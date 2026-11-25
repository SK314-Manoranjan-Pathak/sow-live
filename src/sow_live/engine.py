"""The live loop: build tick prompts, call the sow-live agent, merge results,
and hand lookups to the advisor agent in the background."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from datetime import datetime

from . import knowledge
from .config import Config
from .kiro import KiroError, run_agent
from .session import Session, fmt_ts

RECENT_LINES = 60          # transcript lines re-sent each tick (overlap gives context)
ADVISOR_CONTEXT_FIELDS = ("region", "residency_rules", "compliance", "scale", "users_and_volume",
                          "models", "hosting_choice", "systems", "hosting_connectivity", "data_sources")


class Engine:
    def __init__(self, session: Session, cfg: Config, learnings, *, previous: dict | None = None,
                 on_change=lambda: None):
        self.s = session
        self.cfg = cfg
        self.on_change = on_change
        self.last_index = 0               # first transcript line not yet sent to the agent
        self.tick_lock = threading.Lock()
        self.advisor_pool = ThreadPoolExecutor(max_workers=3, thread_name_prefix="advisor")
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.tick_no = 0
        self.lrn = learnings
        self.previous = previous or {}

    @property
    def learnings(self) -> str:
        return self.lrn.text()

    def _known_answers(self, recent_rows: list[dict]) -> list[dict]:
        st = self.s.state
        reused = {l.get("answer_id") for l in st["lookups"] if l.get("cached")}
        text = " ".join([Session.render_lines(recent_rows[-25:]), st.get("topic", ""),
                         " ".join(v["value"] for v in st["fields"].values())[:2000]])
        out = []
        for a in knowledge.known_answers(text, limit=6):
            if a["id"] in reused:
                continue
            out.append({k: a[k] for k in ("id", "kind", "label", "query", "headline", "confidence", "age_days")})
        return out

    def _previous_text(self) -> str:
        p = self.previous
        if not p.get("sessions"):
            return "(first call with this customer)"
        calls = [f"- {s['started_at'][:10]}: {s['summary']}" for s in p["sessions"]]
        qs = [f"- {q['text']}" for q in p["questions"]]
        return "Earlier calls:\n" + "\n".join(calls) + "\nStill open after the last call:\n" + ("\n".join(qs) or "- none")

    # ---------------------------------------------------------------- prompt
    def _catalog_text(self) -> str:
        rows = [{"id": f["id"], "label": f["label"], "tier": f["tier"], "ask": f["ask"]} for f in self.s.catalog]
        return json.dumps(rows, ensure_ascii=False)

    def build_prompt(self, mode: str, new_rows: list[dict], recent_rows: list[dict]) -> str:
        st = self.s.state
        questions = [
            {k: q[k] for k in ("id", "text", "state", "priority") if k in q}
            for q in st["questions"] if q["state"] in ("open", "asked", "dismissed")
        ]
        answers = [
            # `internal` (other customers' names etc.) is deliberately not passed on.
            {"id": l["id"], "kind": l["kind"], "query": l["query"],
             **{k: l.get("answer", {}).get(k, "") for k in ("headline", "confidence", "sow_impact", "follow_up_question")}}
            for l in st["lookups"] if l["state"] == "done"
        ]
        pending = [{"id": l["id"], "query": l["query"]} for l in st["lookups"] if l["state"] in ("pending", "running")]
        # Live ticks get a compact brief (value + status); the final pass also gets evidence.
        if mode == "final":
            brief = st["fields"]
        else:
            brief = {k: {"value": v["value"], "status": v["status"]} for k, v in st["fields"].items()}
        flags = [{"id": f["id"], "text": f["text"]} for f in st["flags"]]
        parts = [
            f"SESSION: MODE={mode} client={st['client']} minutes_elapsed={self.s.call_elapsed() / 60:.0f} "
            f"minutes_remaining={max(0, self.s.minutes_remaining()):.0f} call_minutes={st['call_minutes']}",
            f"FIELD CATALOG:\n{self._catalog_text()}",
            f"PRE-CALL CONTEXT:\n{self.s.context.strip() or '(none provided)'}",
            f"TEAM LEARNINGS:\n{self.learnings}",
            f"CURRENT BRIEF:\n{json.dumps(brief, ensure_ascii=False)}",
            f"FLAGS ALREADY RAISED (do not repeat or rephrase these; only raise genuinely new risks):\n"
            f"{json.dumps(flags, ensure_ascii=False)}",
            f"QUESTIONS:\n{json.dumps(questions, ensure_ascii=False)}",
            f"ADVISOR ANSWERS:\n{json.dumps(answers, ensure_ascii=False)}",
            f"LOOKUPS IN PROGRESS (do not repeat):\n{json.dumps(pending, ensure_ascii=False)}",
            f"SA NOTES:\n{json.dumps(st['notes'], ensure_ascii=False)}",
            f"ROLLING SUMMARY:\n{st['summary'] or '(none yet)'}",
            f"PREVIOUS CALLS:\n{self._previous_text()}",
            f"LEARNINGS TOPICS COVERED:\n{json.dumps(self.lrn.data.get('topics', []), ensure_ascii=False)}",
        ]
        if mode != "final":
            parts.append(f"KNOWN ANSWERS:\n{json.dumps(self._known_answers(recent_rows), ensure_ascii=False)}")
        if mode == "final":
            parts.append(f"FULL TRANSCRIPT:\n{Session.render_lines(self.s.transcript()) or '(empty)'}")
        elif mode != "kickoff":
            earlier = [r for r in recent_rows if r["i"] < (new_rows[0]["i"] if new_rows else 10**9)]
            parts.append(f"EARLIER LINES (already processed, for context):\n{Session.render_lines(earlier) or '(none)'}")
            parts.append(f"RECENT TRANSCRIPT (new since last call):\n{Session.render_lines(new_rows) or '(no new speech)'}")
        parts.append("Reply with the JSON object only.")
        return "\n\n".join(parts)

    # ---------------------------------------------------------------- ticks
    def current_mode(self) -> str:
        if self.s.state["ended"]:
            return "final"
        if self.s.minutes_remaining() <= self.cfg["closing_minutes"]:
            return "closing"
        return "live"

    def tick(self, mode: str | None = None) -> bool:
        """Run one agent call. Returns True if it merged a result."""
        with self.tick_lock:
            mode = mode or self.current_mode()
            all_rows = self.s.transcript()
            new_rows = [r for r in all_rows if r["i"] >= self.last_index]
            if mode in ("live", "closing") and not new_rows and not self._sa_changed():
                return False
            recent = all_rows[-RECENT_LINES:]
            prompt = self.build_prompt(mode, new_rows, recent)
            self.tick_no += 1
            model = self.cfg["models"]["final" if mode == "final" else "live"]
            self.s.status["agent"] = f"thinking ({mode})"
            self.on_change()
            try:
                out = run_agent(
                    "sow-live", prompt, model=model,
                    timeout=self.cfg["kiro_timeout_seconds"] * (3 if mode == "final" else 1),
                    log_path=self.s.ticks_dir / f"{self.tick_no:04d}-{mode}.md",
                )
            except KiroError as e:
                self.s.status["agent"] = f"error: {e}"
                self.on_change()
                return False
            if new_rows:
                self.last_index = new_rows[-1]["i"] + 1
            self.s.state["mode"] = mode
            self.s.merge_tick(out)
            self._sa_snapshot = self._sa_fingerprint()
            self._reuse(out.get("reuse_answer_ids") or [])
            for lookup in self.s.new_lookups(out):
                if lookup["kind"] == "learnings_refresh":
                    self.advisor_pool.submit(self._refresh_learnings, lookup)
                else:
                    self.advisor_pool.submit(self._advise, lookup)
            self.s.status["agent"] = f"updated {time.strftime('%H:%M:%S')} ({out.get('_took', '?')}s)"
            self.on_change()
            return True

    def _sa_fingerprint(self):
        st = self.s.state
        return (len(st["notes"]), tuple((q["id"], q["state"]) for q in st["questions"]),
                tuple((l["id"], l["state"]) for l in st["lookups"]),
                self.lrn.source, len(self.lrn.data.get("entries", [])))

    def _sa_changed(self) -> bool:
        return getattr(self, "_sa_snapshot", None) != self._sa_fingerprint()

    def run_background(self) -> None:
        def loop():
            last = 0.0
            while not self.stop_event.is_set():
                rows = self.s.transcript(self.last_index)
                words = sum(len(r["text"].split()) for r in rows)
                due = time.time() - last >= self.cfg["tick_seconds"]
                if (due and (rows or self._sa_changed())) or words >= self.cfg["min_new_words_for_tick"] * 4:
                    last = time.time()
                    self.tick()
                self.stop_event.wait(2)

        self.thread = threading.Thread(target=loop, name="ticker", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=self.cfg["kiro_timeout_seconds"] + 5)

    # ---------------------------------------------------------------- advisor
    def ask_advisor(self, query: str, kind: str = "customer_question") -> None:
        """SA-initiated lookup from the panel (`?` = AWS advisor, `w` = org wiki)."""
        lid = f"l-sa-{int(time.time() * 1000)}"
        rec = {"id": lid, "kind": kind, "query": query,
               "ts": "", "state": "pending", "by_sa": True}
        with self.s.lock:
            self.s.state["lookups"].append(rec)
            self.s.save()
        self.advisor_pool.submit(self._advise, rec)
        self.on_change()

    def _advise(self, lookup: dict) -> None:
        self.s.set_lookup(lookup["id"], state="running")
        self.on_change()
        st = self.s.state
        ctx_fields = {k: st["fields"][k]["value"] for k in ADVISOR_CONTEXT_FIELDS if k in st["fields"]}
        rows = self.s.transcript()
        excerpt = rows[-12:]
        if lookup.get("ts"):
            idx = next((r["i"] for r in rows if r["ts"] >= lookup["ts"]), None)
            if idx is not None:
                excerpt = [r for r in rows if idx - 8 <= r["i"] <= idx + 3]
        org = lookup["kind"] == "org_experience"
        parts = [
            f"KIND: {lookup['kind']}",
            f"QUERY: {lookup['query']}",
            f"CALL CONTEXT:\nsummary: {st['summary'] or '(none)'}\nfields: {json.dumps(ctx_fields, ensure_ascii=False)}\n"
            f"pre-call context: {self.s.context.strip()[:3000] or '(none)'}",
            f"TRANSCRIPT EXCERPT:\n{Session.render_lines(excerpt) or '(none)'}",
        ]
        if not org:
            parts.append(f"TEAM LEARNINGS:\n{self.learnings}")
        parts.append("Reply with the JSON object only.")
        agent, model_key = ("sow-live-org", "org") if org else ("sow-live-advisor", "advisor")
        try:
            ans = run_agent(
                agent, "\n\n".join(parts), model=self.cfg["models"].get(model_key),
                timeout=self.cfg["kiro_timeout_seconds"],
                log_path=self.s.ticks_dir / f"{'org' if org else 'advisor'}-{lookup['id']}.md", trust_tools=True,
            )
            self.s.set_lookup(lookup["id"], state="done", answer=ans,
                              answered_at=datetime.now().isoformat(timespec="seconds"))
        except KiroError as e:
            self.s.set_lookup(lookup["id"], state="error", error=str(e))
        self.on_change()

    # ---------------------------------------------------------------- knowledge graph + learnings
    def _reuse(self, ids: list[str]) -> None:
        """Surface answers verified on earlier calls without a new lookup."""
        max_age = self.cfg.get("known_answer_max_age_days", 30)
        with self.s.lock:
            have = {l.get("answer_id") for l in self.s.state["lookups"]}
            for aid in ids:
                if aid in have:
                    continue
                a = knowledge.get_answer(aid)
                if not a or a["age_days"] > max_age:
                    continue
                self.s.state["lookups"].append({
                    "id": f"l-cached-{aid}", "kind": a["kind"], "label": a["label"], "query": a["query"],
                    "ts": fmt_ts(self.s.call_elapsed()), "state": "done", "cached": True, "answer_id": aid,
                    "age_days": a["age_days"], "answer": {k: a[k] for k in (
                        "headline", "detail", "confidence", "sources", "sow_impact", "follow_up_question")},
                })
            self.s.save()

    def _refresh_learnings(self, lookup: dict) -> None:
        if self.lrn.source == "fallback":
            self.s.set_lookup(lookup["id"], state="done", answer={"headline": "skipped: wiki unreachable"})
            return
        self.s.set_lookup(lookup["id"], state="running")
        self.s.status["learnings"] = f"fetching wiki lessons: {lookup.get('label') or lookup['query'][:40]}"
        self.on_change()
        found = self.lrn.fetch(lookup["query"], self.s.state.get("summary", ""), refresh=True,
                               log_path=self.s.ticks_dir / f"learnings-{lookup['id']}.md")
        self.s.set_lookup(lookup["id"], state="done", answer={"headline": f"{'added' if found else 'no new'} lessons"})
        self.s.status.pop("learnings", None)
        self.on_change()
