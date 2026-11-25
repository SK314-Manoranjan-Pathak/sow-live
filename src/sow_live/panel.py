"""Floating-terminal panel for the SA. Renders session state with rich and
reads one command line at a time from the keyboard."""

from __future__ import annotations

import os
import select
import sys
import termios
import threading
import time
import tty

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .session import fmt_ts

HELP = ("a N asked · x N answered · d N dismiss · p N pin · n <note> · ? <AWS question> · w <wiki question> · "
        "e N expand answer · go call started · r refresh · end finish call · quit")

LEVEL_CHARS = " ▁▂▃▄▅▆▇█"


def _meter(level: float) -> str:
    idx = min(len(LEVEL_CHARS) - 1, int(level * 60))
    return LEVEL_CHARS[idx]


class Panel_:
    def __init__(self, session, engine, capture_status: dict, *, on_end, on_quit, title: str = ""):
        self.s = session
        self.engine = engine
        self.status = capture_status
        self.on_end = on_end
        self.on_quit = on_quit
        self.title = title
        self.buffer = ""
        self.message = "Kickoff: reading your context and planning questions..."
        self.expanded: str | None = None
        self.console = Console()
        self.done = threading.Event()
        self._shown_questions: list[dict] = []
        self._shown_lookups: list[dict] = []

    # ---------------------------------------------------------------- render
    def render(self):
        st = self.s.state
        width = self.console.size.width
        height = self.console.size.height
        cf, ct, imf, imt = self.s.coverage()
        mode = st["mode"].upper()
        started = st.get("call_started_epoch")
        clock = (f"{fmt_ts(self.s.call_elapsed())} in · {max(0, self.s.minutes_remaining()):.0f} min left"
                 if started else "call not started")
        mode_style = {"KICKOFF": "cyan", "LIVE": "green", "CLOSING": "bold red", "FINAL": "magenta"}.get(mode, "white")

        head = Text()
        head.append(" SoW Live ", "bold black on cyan")
        head.append(f"  {self.title or st['client']}  ", "bold")
        head.append(f"{clock}  ")
        head.append(f"[{mode}]", mode_style)
        head.append(f"   critical {cf}/{ct}", "green" if cf == ct else "yellow")
        head.append(f" · important {imf}/{imt}", "dim")

        stat = Text(style="dim")
        stat.append(f"topic: {st.get('topic') or '-'}   agent: {self.s.status.get('agent', 'idle')}   ")
        asr = self.status.get("asr", "off")
        stat.append(f"asr: {asr}")
        if self.status.get("asr_queue"):
            stat.append(f" (q{self.status['asr_queue']})")
        stat.append(f"   learnings: {self.s.status.get('learnings') or self.engine.lrn.status_line()}",
                    "" if self.engine.lrn.source == "wiki" else "yellow")
        if "wiki" in self.status:
            stat.append(f"   wiki: {self.status['wiki']}", "" if self.status["wiki"] == "ok" else "yellow")
        for who in ("SA", "Remote"):
            if who in self.status:
                stat.append(f"   {who} {_meter(self.status.get(who + '_level', 0))} {self.status[who]}")

        # Questions
        qs = self.s.open_questions()
        limit = self.engine.cfg["max_open_questions_shown"]
        if st["mode"] == "closing":
            qs = [q for q in qs if q.get("priority", 2) == 1 or q["state"] == "asked" or q.get("pinned")] or qs
        self._shown_questions = qs[:limit]
        qt = Table.grid(padding=(0, 1), expand=True)
        qt.add_column(width=3, justify="right")
        qt.add_column(width=2)
        qt.add_column(ratio=1)
        for i, q in enumerate(self._shown_questions, 1):
            pr = q.get("priority", 2)
            marker = "📌" if q.get("pinned") else ("⏳" if q["state"] == "asked" else {1: "●", 2: "○", 3: "·"}[pr])
            style = "bold" if pr == 1 and q["state"] == "open" else ("dim" if q["state"] == "asked" else "")
            body = Text(q["text"], style=style)
            if q.get("why"):
                body.append(f"\n{q['why']}", "dim italic")
            qt.add_row(Text(str(i), "cyan"), marker, body)
        more = len(qs) - len(self._shown_questions)
        q_title = "Ask next" + (f"  (+{more} more)" if more > 0 else "")
        questions = Panel(qt if self._shown_questions else Text("No open questions yet.", "dim"),
                          title=q_title, title_align="left", border_style="cyan")

        # Answers from the advisor
        lks = [l for l in reversed(st["lookups"])
               if l["state"] != "superseded" and l["kind"] != "learnings_refresh"][:3]
        self._shown_lookups = lks
        at = Table.grid(padding=(0, 1), expand=True)
        at.add_column(width=3, justify="right")
        at.add_column(ratio=1)
        newest_done = next((l["id"] for l in lks if l["state"] == "done"), None)
        for i, l in enumerate(lks, 1):
            org = l["kind"] == "org_experience"
            src_tag = ("[wiki]" if org else "[aws]") + (f" ⟲{l.get('age_days', 0)}d" if l.get("cached") else "")
            label = "Customer asked" if l["kind"] in ("customer_question", "org_experience") else "Check"
            if l.get("by_sa"):
                label = "You asked"
            if l.get("cached"):
                label = "From an earlier call"
            what = l.get("label") or l["query"]
            what = what if len(what) <= width - 38 else what[: width - 41] + "..."
            body = Text(f"{src_tag} ", "bold blue" if org else "bold magenta")
            body.append(f"{label}: {what}\n", "dim")
            if l["state"] in ("pending", "running"):
                body.append("searching the ShellKode wiki..." if org else "looking up AWS docs...", "yellow")
            elif l["state"] == "error":
                body.append(f"lookup failed: {l.get('error', '')}", "red")
            else:
                a = l.get("answer", {})
                conf = a.get("confidence", "?")
                body.append(a.get("headline", ""), "bold")
                body.append(f"  [{conf}]", {"confirmed": "green", "found": "green", "partial": "yellow"}.get(conf, "red"))
                if self.expanded == l["id"] or (self.expanded is None and l["id"] == newest_done):
                    for d in a.get("detail", [])[:3]:
                        body.append(f"\n  • {d}")
                    for d in (a.get("internal") or [])[:4]:
                        body.append(f"\n  🔒 {d}", "italic red")
                    if a.get("follow_up_question"):
                        body.append(f"\n  ↳ ask: {a['follow_up_question']}", "cyan")
                    if a.get("sources"):
                        body.append(f"\n  source: {a['sources'][0].get('url', '')}"
                                    + (f" (+{len(a['sources']) - 1})" if len(a["sources"]) > 1 else ""), "dim")
            at.add_row(Text(f"e{i}", "magenta"), body)
        answers = Panel(at if lks else Text("Customer questions appear here, answered from AWS docs [aws] or the ShellKode "
                                            "wiki [wiki]. Type ? <question> (AWS) or w <question> (wiki) yourself.", "dim"),
                        title="Answers   🔒 = internal, don't say on the call", title_align="left", border_style="magenta")

        # Flags
        flags = st["flags"][-3:]
        ft = Text()
        for f in flags:
            ft.append(f"⚠ {f['text']}\n", "yellow")
        flag_panel = Panel(ft if flags else Text("none", "dim"), title="Flags", title_align="left",
                           border_style="yellow")

        # Transcript tail
        rows = self.s.transcript(max(0, st["transcript_count"] - 4))
        tt = Text()
        for r in rows:
            tt.append(f"[{r['ts']}] ", "dim")
            tt.append(f"{r['speaker']}: ", "cyan" if r["speaker"] == "SA" else "green")
            tt.append(r["text"][: max(40, width - 22)] + "\n")
        transcript = Panel(tt if rows else Text("waiting for speech...", "dim"), title="Transcript",
                           title_align="left", border_style="dim")

        if self.message.startswith("Kickoff") and st["mode"] != "kickoff":
            self.message = "Ready. Questions update as the call goes."
        prompt = Text()
        prompt.append("> ", "bold cyan")
        prompt.append(self.buffer)
        prompt.append("▌", "blink")
        foot = Group(prompt, Text(self.message, "italic"), Text(HELP, "dim"))

        parts = [head, stat, questions, answers]
        if height >= 38:
            parts.append(flag_panel)
        if height >= 46:
            parts.append(transcript)
        elif flags and height < 38:
            parts.insert(2, Text(f"⚠ {flags[-1]['text']}", "yellow"))
        parts.append(foot)
        return Group(*parts)

    # ---------------------------------------------------------------- commands
    def _q(self, arg: str):
        try:
            return self._shown_questions[int(arg) - 1]
        except (ValueError, IndexError):
            self.message = f"No question #{arg}"
            return None

    def handle(self, line: str) -> None:
        line = line.strip()
        if not line:
            return
        cmd, _, arg = line.partition(" ")
        cmd = cmd.lower()
        if cmd in ("a", "x", "d", "p") and arg:
            q = self._q(arg.strip())
            if q:
                new = {"a": "asked", "x": "answered", "d": "dismissed", "p": "pinned"}[cmd]
                self.s.set_question_state(q["id"], new)
                self.message = f"{new}: {q['text'][:70]}"
        elif cmd == "n" and arg:
            self.s.add_note(arg)
            self.message = "Note saved. The agent treats notes as confirmed facts."
        elif line.startswith("?"):
            query = line[1:].strip()
            if query:
                self.engine.ask_advisor(query)
                self.message = "Looking it up in AWS docs..."
        elif cmd == "w" and arg:
            self.engine.ask_advisor(arg.strip(), kind="org_experience")
            self.message = "Searching the ShellKode wiki..."
        elif cmd == "e" or (cmd.startswith("e") and cmd[1:].isdigit()):
            n = arg or cmd[1:]
            try:
                self.expanded = self._shown_lookups[int(n) - 1]["id"]
            except (ValueError, IndexError):
                self.message = f"No answer e{n}"
        elif cmd == "go":
            self.s.mark_call_started()
            self.message = "Call clock started."
        elif cmd == "r":
            threading.Thread(target=self.engine.tick, daemon=True).start()
            self.message = "Refreshing..."
        elif cmd == "end":
            self.message = "Ending call..."
            self.done.set()
            self.on_end()
        elif cmd == "quit":
            self.done.set()
            self.on_quit()
        else:
            self.message = f"Unknown command: {line}"

    # ---------------------------------------------------------------- loop
    def run(self) -> None:
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            with Live(self.render(), console=self.console, screen=True, auto_refresh=False) as live:
                last = 0.0
                while not self.done.is_set():
                    r, _, _ = select.select([sys.stdin], [], [], 0.25)
                    if r:
                        ch = os.read(fd, 1).decode(errors="ignore")
                        if ch in ("\n", "\r"):
                            line, self.buffer = self.buffer, ""
                            self.handle(line)
                        elif ch in ("\x7f", "\b"):
                            self.buffer = self.buffer[:-1]
                        elif ch == "\x1b":
                            self.buffer = ""
                        elif ch.isprintable():
                            self.buffer += ch
                    if r or time.time() - last > 0.5:
                        live.update(self.render(), refresh=True)
                        last = time.time()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
