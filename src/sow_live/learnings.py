"""Team learnings come from the ShellKode wiki (Challenges / Solutions / Playbooks).

The org agent builds a digest for an engagement before the call and saves it to
<engagement>/build/learnings.json + learnings.md. Live ticks, the advisor and the
SoW pipeline all read that digest. If the wiki can't be reached, a generic
built-in fallback is used and labelled as such.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime

from .config import Config, framework_file
from .kiro import KiroError, run_agent


class Learnings:
    def __init__(self, engagement, cfg: Config):
        self.e = engagement
        self.cfg = cfg
        self.lock = threading.Lock()
        self.json_path = engagement.build / "learnings.json"
        self.md_path = engagement.build / "learnings.md"
        self.data = {"source": "none", "entries": [], "topics": [], "updated": "", "error": ""}
        if self.json_path.exists():
            try:
                self.data = json.loads(self.json_path.read_text())
            except json.JSONDecodeError:
                pass

    # ---------------------------------------------------------------- state
    @property
    def source(self) -> str:
        return self.data.get("source", "none")

    def status_line(self) -> str:
        if self.source == "wiki":
            return f"wiki ({len(self.data['entries'])})"
        if self.source == "fallback":
            return "generic fallback (wiki unreachable)"
        return "loading"

    def text(self) -> str:
        """Learnings text for agent prompts."""
        if self.source == "wiki" and self.data["entries"]:
            return self._render_entries(self.data["entries"])
        return framework_file("live", "fallback-learnings.md").read_text()

    @staticmethod
    def _render_entries(entries: list[dict]) -> str:
        lines = []
        for e in entries:
            lines.append(f"### [{e.get('category', 'General')}] {e.get('title', '')}")
            lines.append(f"- What: {e.get('what', '')}")
            lines.append(f"- Action: {e.get('action', '')}")
            if e.get("url"):
                lines.append(f"- Wiki: {e['url']}")
            lines.append("")
        return "\n".join(lines).strip()

    def save(self) -> None:
        self.e.build.mkdir(parents=True, exist_ok=True)
        self.json_path.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))
        if self.source == "wiki":
            head = (f"# Learnings for {self.e.title}\n\n> **Source: ShellKode wiki** digest, updated "
                    f"{self.data['updated']}. Topics: {', '.join(self.data['topics']) or '-'}. Each entry links to "
                    "its wiki page. Refresh with `sow-live learnings`.\n\n")
            self.md_path.write_text(head + self._render_entries(self.data["entries"]) + "\n")
        else:
            note = f"\n> Wiki error: {self.data['error']}\n" if self.data.get("error") else ""
            self.md_path.write_text(framework_file("live", "fallback-learnings.md").read_text() + note)

    # ---------------------------------------------------------------- fetch
    def fetch(self, topics: str, context: str = "", log_path=None, refresh: bool = False) -> bool:
        """Ask the org agent for wiki lessons on `topics`. Merges into the digest."""
        prompt = "\n\n".join([
            "KIND: learnings_digest",
            f"QUERY: {topics}",
            f"CALL CONTEXT:\nengagement: {self.e.title}\n{context.strip()[:4000] or '(none)'}",
            "ALREADY IN DIGEST:\n" + json.dumps([x.get("title") for x in self.data["entries"]], ensure_ascii=False),
            "Reply with the JSON object only.",
        ])
        try:
            out = run_agent("sow-live-org", prompt, model=self.cfg["models"].get("org"),
                            timeout=self.cfg["kiro_timeout_seconds"] * 2, log_path=log_path, trust_tools=True)
        except KiroError as ex:
            out = {"learnings": [], "confidence": "none", "error": str(ex)}
        entries = [x for x in out.get("learnings") or [] if x.get("title") and x.get("what")]
        with self.lock:
            now = datetime.now().isoformat(timespec="minutes")
            wiki_ok = not out.get("error") and out.get("confidence") in ("found", "partial", "none")
            if entries or (wiki_ok and self.source != "wiki" and not out.get("error")):
                known = {x["title"].lower() for x in self.data["entries"]}
                merged = list(self.data["entries"]) if self.source == "wiki" else []
                merged += [x for x in entries if x["title"].lower() not in known]
                self.data.update(source="wiki", entries=merged, updated=now, error="")
                self.data["topics"] = sorted(set(self.data.get("topics", [])) | {topics[:80]})
            elif not refresh:
                self.data.update(source="fallback", updated=now, error=out.get("error") or "no wiki results")
            self.save()
        return bool(entries)
