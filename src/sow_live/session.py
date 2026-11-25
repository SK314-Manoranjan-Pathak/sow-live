"""Session state. Everything lives in files under <engagement>/live/<session>/ so a
call is auditable and can be finalized again later."""

from __future__ import annotations

import json
import re
import threading
import time
from datetime import datetime
from pathlib import Path

from .config import load_catalog


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "client"


def fmt_ts(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


class Session:
    """Thread-safe call state. Mutate only through methods (they take the lock)."""

    def __init__(self, path: Path, state: dict):
        self.path = path
        self.state = state
        self.lock = threading.RLock()
        self.catalog = load_catalog()
        self.catalog_by_id = {f["id"]: f for f in self.catalog}
        self.t0 = state["started_epoch"]
        self.ticks_dir = path / "ticks"
        self.ticks_dir.mkdir(exist_ok=True)
        self.status: dict[str, str] = {}  # transient UI status lines

    # ---------------------------------------------------------------- create/load
    @classmethod
    def create(cls, engagement, call_minutes: int, context: str, context_sources: list[str]) -> "Session":
        stamp = datetime.now().strftime("%Y%m%d-%H%M")
        path = engagement.live / stamp
        n = 2
        while path.exists():
            path = engagement.live / f"{stamp}-{n}"
            n += 1
        path.mkdir(parents=True)
        client = engagement.client
        (path / "context.md").write_text(context)
        state = {
            "client": client,
            "engagement": engagement.slug,
            "engagement_path": str(engagement.path),
            "call_minutes": call_minutes,
            "started_epoch": time.time(),
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "context_sources": context_sources,
            "mode": "kickoff",
            "topic": "",
            "summary": "",
            "fields": {},
            "questions": [],
            "flags": [],
            "lookups": [],
            "notes": [],
            "transcript_count": 0,
            "ended": False,
        }
        s = cls(path, state)
        s.save()
        return s

    @classmethod
    def load(cls, path: Path) -> "Session":
        return cls(path, json.loads((path / "state.json").read_text()))

    @property
    def context(self) -> str:
        p = self.path / "context.md"
        return p.read_text() if p.exists() else ""

    def save(self) -> None:
        with self.lock:
            tmp = self.path / "state.json.tmp"
            tmp.write_text(json.dumps(self.state, indent=2, ensure_ascii=False))
            tmp.replace(self.path / "state.json")

    # ---------------------------------------------------------------- time
    def elapsed(self) -> float:
        return time.time() - self.t0

    def call_elapsed(self) -> float:
        """Seconds since the call itself started (first customer speech, or `go`)."""
        started = self.state.get("call_started_epoch")
        return time.time() - started if started else 0.0

    def mark_call_started(self) -> None:
        with self.lock:
            if not self.state.get("call_started_epoch"):
                self.state["call_started_epoch"] = time.time()
                self.save()

    def minutes_remaining(self) -> float:
        return self.state["call_minutes"] - self.call_elapsed() / 60

    # ---------------------------------------------------------------- follow-up calls
    def seed_from_previous(self, previous: dict) -> None:
        """Start a follow-up call from what earlier calls with this customer captured."""
        with self.lock:
            for fid, f in previous.get("facts", {}).items():
                if fid in self.catalog_by_id and f.get("value"):
                    self.state["fields"][fid] = {
                        "value": f["value"], "status": "previous_call", "evidence": f.get("evidence", ""),
                        "conflict": "", "updated": f"earlier call ({(f.get('updated_at') or '')[:10]})"}
            for q in previous.get("questions", []):
                self.state["questions"].append({
                    "id": q["id"], "text": q["text"], "why": q.get("why", ""), "field_ids": [],
                    "priority": q.get("priority", 2), "state": "open", "created": "earlier call"})
            for f in previous.get("flags", []):
                self.state["flags"].append({**f, "ts": "earlier call"})
            self.save()

    # ---------------------------------------------------------------- transcript
    def add_utterance(self, speaker: str, start: float, text: str) -> dict:
        with self.lock:
            idx = self.state["transcript_count"]
            u = {"i": idx, "ts": fmt_ts(start), "t": round(start, 1), "speaker": speaker, "text": text}
            with open(self.path / "transcript.jsonl", "a") as f:
                f.write(json.dumps(u, ensure_ascii=False) + "\n")
            with open(self.path / "transcript.md", "a") as f:
                f.write(f"[{u['ts']}] {speaker}: {text}\n")
            self.state["transcript_count"] = idx + 1
            if speaker == "Remote" and not self.state.get("call_started_epoch"):
                self.state["call_started_epoch"] = time.time()
            self.save()
            return u

    def transcript(self, since: int = 0) -> list[dict]:
        p = self.path / "transcript.jsonl"
        if not p.exists():
            return []
        rows = [json.loads(line) for line in p.read_text().splitlines() if line.strip()]
        return [r for r in rows if r["i"] >= since]

    @staticmethod
    def render_lines(rows: list[dict]) -> str:
        return "\n".join(f"[{r['ts']}] {r['speaker']}: {r['text']}" for r in rows)

    # ---------------------------------------------------------------- SA actions
    def add_note(self, text: str) -> None:
        with self.lock:
            self.state["notes"].append({"ts": fmt_ts(self.elapsed()), "text": text})
            self.save()

    def open_questions(self) -> list[dict]:
        with self.lock:
            qs = [q for q in self.state["questions"] if q["state"] in ("open", "asked")]
            return sorted(qs, key=lambda q: (not q.get("pinned"), q["state"] == "asked", q.get("priority", 2)))

    def set_question_state(self, qid: str, new_state: str) -> None:
        with self.lock:
            for q in self.state["questions"]:
                if q["id"] == qid:
                    if new_state == "pinned":
                        q["pinned"] = not q.get("pinned", False)
                    else:
                        q["state"] = new_state
            self.save()

    # ---------------------------------------------------------------- merge agent output
    def merge_tick(self, out: dict) -> None:
        with self.lock:
            st = self.state
            st["topic"] = out.get("topic") or st["topic"]
            st["summary"] = out.get("summary") or st["summary"]

            for f in out.get("fields") or []:
                fid = f.get("id")
                if fid not in self.catalog_by_id or not f.get("value"):
                    continue
                prev = st["fields"].get(fid)
                rec = {
                    "value": f["value"],
                    "status": f.get("status", "inferred"),
                    "evidence": f.get("evidence", ""),
                    "conflict": f.get("conflict", ""),
                    "updated": fmt_ts(self.elapsed()),
                }
                if prev and prev.get("value") != rec["value"] and not rec["conflict"]:
                    rec["previous"] = prev.get("value")
                st["fields"][fid] = rec

            resolved = set(out.get("resolved_question_ids") or [])
            by_id = {q["id"]: q for q in st["questions"]}
            for q in st["questions"]:
                if q["id"] in resolved and q["state"] in ("open", "asked"):
                    q["state"] = "answered"
                    q["answered_at"] = fmt_ts(self.elapsed())

            returned = out.get("questions")
            if returned is not None:
                keep_ids = set()
                for q in returned:
                    qid = q.get("id")
                    if not qid or not q.get("text") or qid in resolved:
                        continue
                    keep_ids.add(qid)
                    if qid in by_id:
                        cur = by_id[qid]
                        if cur["state"] in ("dismissed", "answered"):
                            continue
                        cur.update({k: q[k] for k in ("text", "why", "field_ids", "priority") if k in q})
                    else:
                        new = {
                            "id": qid,
                            "text": q["text"],
                            "why": q.get("why", ""),
                            "field_ids": q.get("field_ids", []),
                            "priority": q.get("priority", 2),
                            "state": "open",
                            "created": fmt_ts(self.elapsed()),
                        }
                        st["questions"].append(new)
                        by_id[qid] = new
                # Open suggestions the agent dropped are superseded, unless the SA acted on them.
                for q in st["questions"]:
                    if q["state"] == "open" and q["id"] not in keep_ids and not q.get("pinned"):
                        q["state"] = "superseded"

            known_flags = {f["id"] for f in st["flags"]}
            for f in out.get("flags") or []:
                if (f.get("id") and f["id"] not in known_flags and f.get("text")
                        and f["text"] not in {x["text"] for x in st["flags"]}):
                    st["flags"].append({**f, "ts": fmt_ts(self.elapsed())})
                    known_flags.add(f["id"])

            for key in ("assumptions", "open_items", "followup_email", "entities"):
                if key in out:
                    st[key] = out[key]
            self.save()

    def new_lookups(self, out: dict) -> list[dict]:
        """Register lookups from a tick; returns the ones not seen before."""
        with self.lock:
            known = {l["id"] for l in self.state["lookups"]}
            fresh = []
            for l in out.get("lookups") or []:
                if l.get("id") and l.get("query") and l["id"] not in known:
                    rec = {
                        "id": l["id"],
                        "kind": l.get("kind", "customer_question"),
                        "label": l.get("label", ""),
                        "query": l["query"],
                        "ts": l.get("ts") or fmt_ts(self.elapsed()),
                        "state": "pending",
                    }
                    self.state["lookups"].append(rec)
                    fresh.append(rec)
                    known.add(l["id"])
            self.save()
            return fresh

    def set_lookup(self, lid: str, **updates) -> None:
        with self.lock:
            for l in self.state["lookups"]:
                if l["id"] == lid:
                    l.update(updates)
            self.save()

    # ---------------------------------------------------------------- coverage
    def coverage(self) -> tuple[int, int, int, int]:
        """(critical filled, critical total, important filled, important total) for call fields."""
        with self.lock:
            filled = {k for k, v in self.state["fields"].items()
                      if v.get("status") not in ("inferred",) and v.get("value")}
            crit = [f["id"] for f in self.catalog if f["ask"] == "call" and f["tier"] == "critical"]
            imp = [f["id"] for f in self.catalog if f["ask"] == "call" and f["tier"] == "important"]
            return (len([c for c in crit if c in filled]), len(crit), len([i for i in imp if i in filled]), len(imp))
