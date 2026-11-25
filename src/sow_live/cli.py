"""sow-live command line.

Setup:        sow-live init | auth | check | wiki-login | wiki-seed | uninstall
Engagements:  sow-live new "Client" "Project" | list | open <name> | import <folder>
Calls:        sow-live start [--client NAME] [--minutes 60] | finalize [name]
SoW:          sow-live generate [name] | learnings [name]
Engine tools: sow-live docx | diagram | preview | mcp   (used by the Kiro skills)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from . import __version__
from . import engagements as eng_mod
from .config import FRAMEWORK, KIRO_HOME, SOW_HOME, SYSCAP_BIN, USER_CONFIG, Config, framework_file
from .session import Session

ADMIN_PROMPTS = [
    ("client_legal_name", "Client legal name"),
    ("client_short_name", "Client short name"),
    ("client_address", "Registered office address"),
    ("effective_date", "Effective date"),
    ("expiration_date", "Expiration date"),
    ("author", "Author / preparer"),
]


def _say(msg: str) -> None:
    print(f"\033[36m›\033[0m {msg}", flush=True)


def _tty() -> bool:
    return sys.stdin.isatty()


def _require_setup() -> bool:
    if not FRAMEWORK.exists():
        _say("sow-live is not set up yet. Run: sow-live init")
        return False
    return True


def _engagement(query: str | None, *, create: bool = False, interactive: bool | None = None):
    interactive = _tty() if interactive is None else interactive
    e = eng_mod.resolve(query, interactive=interactive, create_if_missing=create)
    if e is None:
        _say(f"No engagement found{f' for {query!r}' if query else ''}. "
             "Create one with: sow-live new \"Client\" \"Project\"")
        return None
    e.ensure_scaffold()
    return e


# ------------------------------------------------------------------ context
def gather_context(args, e) -> tuple[str, list[str]]:
    from . import context

    if args.context:
        return args.context, ["typed (--context)"]
    if args.context_file:
        p = Path(args.context_file)
        return p.read_text(errors="ignore"), [str(p)]
    text, used, skipped = context.from_sol(e.sol)
    if used:
        _say(f"Using {len(used)} file(s) from {e.slug}/sol: {', '.join(used)}")
        if skipped:
            _say(f"Skipped (unreadable or too large): {', '.join(skipped)}")
        if _tty() and not args.headless:
            extra = input("Anything to add before the call? (Enter to skip) ").strip()
            if extra:
                text += f"\n\n### Typed by SA before the call\n{extra}"
                used.append("typed")
        return text, used
    if _tty() and not args.headless:
        typed = context.prompt_typed()
        if typed:
            (e.sol / "pre-call-notes.md").write_text(typed + "\n")
            _say(f"Saved your notes to {e.slug}/sol/pre-call-notes.md")
        return typed, ["typed"] if typed else []
    return "", []


def topics_for(e, context: str) -> str:
    """Topics for the wiki learnings digest: the engagement and its pre-call context."""
    flat = re.sub(r"\s+", " ", context)[:1200]
    return f"{e.title}. {flat}"


# ------------------------------------------------------------------ transcript replay (testing)
LINE_RE = re.compile(r"^\s*(?:\[(?P<ts>[\d:]+)\]\s*)?(?P<who>[^:]{1,40}):\s*(?P<text>.+)$")


def _parse_ts(ts: str) -> float:
    secs = 0
    for p in ts.split(":"):
        secs = secs * 60 + int(p)
    return float(secs)


def replay_transcript(path: str, session: Session, speed: float, done: threading.Event) -> None:
    rows = []
    for line in Path(path).read_text().splitlines():
        m = LINE_RE.match(line)
        if not m:
            continue
        who = m["who"].strip()
        speaker = "SA" if who.lower() in ("sa", "shellkode", "me") else "Remote"
        rows.append((_parse_ts(m["ts"]) if m["ts"] else None, speaker, m["text"].strip()))
    t_prev = clock = 0.0
    for ts, speaker, text in rows:
        ts = ts if ts is not None else clock + max(2.0, len(text.split()) / 2.5)
        time.sleep(max(0.0, ts - t_prev) / speed)
        t_prev = clock = ts
        session.add_utterance(speaker, ts, text)
    done.set()


# ------------------------------------------------------------------ finalize
def ask_admin(session: Session, cfg: Config, e) -> dict[str, str]:
    st = session.state
    defaults = {"client_legal_name": e.meta.get("legal_name") or e.client, "client_short_name": e.client,
                "author": cfg.get("author") or os.environ.get("SOW_AUTHOR", "")}
    for key in ("client_address", "effective_date", "expiration_date"):
        if e.meta.get(key):
            defaults[key] = e.meta[key]
    print("\nAdmin fields for the Service Agreement (Enter accepts the default or leaves a placeholder):")
    out = {}
    for key, label in ADMIN_PROMPTS:
        d = defaults.get(key) or (st["fields"].get(key) or {}).get("value", "")
        try:
            v = input(f"  {label}{f' [{d}]' if d else ''}: ").strip()
        except EOFError:
            v = ""
        if v or d:
            out[key] = v or d
    # Remember them for the next call with this customer.
    for key in ("client_address", "effective_date", "expiration_date"):
        if out.get(key):
            e.meta[key] = out[key]
    if out.get("client_legal_name"):
        e.meta["legal_name"] = out["client_legal_name"]
    e.save()
    return out


def finalize(session: Session, cfg: Config, e, engine=None, *, interactive: bool, handoff: bool) -> int:
    from . import knowledge
    from .brief import write_outputs
    from .engine import Engine
    from .learnings import Learnings

    engine = engine or Engine(session, cfg, Learnings(e, cfg))
    session.state["ended"] = True
    session.save()
    _say("Call ended. Running the final pass over the full transcript (about a minute)...")
    if not engine.tick("final"):
        _say(f"Final pass failed ({session.status.get('agent')}). Writing the brief from the live state instead.")
    engine.advisor_pool.shutdown(wait=True, cancel_futures=False)  # let in-flight lookups land

    admin = ask_admin(session, cfg, e) if interactive else {
        "client_legal_name": e.meta.get("legal_name") or e.client, "client_short_name": e.client,
        **({"author": cfg.get("author")} if cfg.get("author") else {})}
    paths = write_outputs(session, admin, e.build)
    try:
        counts = knowledge.ingest_session(e, session)
        _say(f"Knowledge graph: {counts['facts']} facts, {counts['answers']} answers, {counts['entities']} entities")
    except Exception as ex:  # never lose the brief over the graph
        _say(f"Knowledge graph update failed: {ex}")

    cf, ct, imf, imt = session.coverage()
    print()
    _say(f"Coverage: critical {cf}/{ct}, important {imf}/{imt}")
    _say(f"Brief:           {paths['brief']}")
    _say(f"Evidence review: {paths['review']}")
    if "email" in paths:
        _say(f"Follow-up email: {paths['email']}")

    if not handoff:
        _say(f"Skipping the SoW pipeline. Run it later with: sow-live generate {e.slug}")
        return 0
    if interactive:
        try:
            ans = input("\nGenerate the SoW now? [Y/n/e = open brief in $EDITOR first] ").strip().lower()
        except EOFError:
            ans = "y"
        if ans == "n":
            _say(f"OK. Run it later with: sow-live generate {e.slug}")
            return 0
        if ans == "e":
            subprocess.call([os.environ.get("EDITOR", "vi"), str(paths["brief"])])
    return generate(cfg, e)


def generate(cfg: Config, e) -> int:
    brief = e.build / "brief.md"
    if brief.exists() and "<!-- source: sow-live -->" in brief.read_text():
        prompt = framework_file("prompts", "handoff-prompt.md").read_text()
    else:
        prompt = ("Create the Statement of Work for this engagement using the sow-generator skill. "
                  "Run the full two-pass workflow and ask me in one grouped round.")
    cmd = ["kiro-cli", "chat", "--trust-workspace"]
    if cfg["pipeline"].get("trust_all_tools"):
        cmd.append("--trust-all-tools")
    cmd.append(prompt)
    _say(f"Handing off to the SoW pipeline in {e.path} ...")
    os.chdir(e.path)
    from .install import kiro_env

    os.execvpe(cmd[0], cmd, kiro_env())
    return 0  # not reached


# ------------------------------------------------------------------ start
def cmd_start(args) -> int:
    if not _require_setup():
        return 1
    cfg = Config.load()
    if args.model:
        cfg.raw["models"]["live"] = args.model
    call_minutes = args.minutes or cfg["default_call_minutes"]
    interactive = _tty() and not args.headless

    e = _engagement(args.client, create=True, interactive=interactive) if args.client else _engagement(
        None, create=True, interactive=interactive)
    if e is None:
        return 1
    _say(f"Engagement: {e.title}  ({e.path})")

    from . import knowledge
    from .audio import Capture
    from .engine import Engine
    from .learnings import Learnings

    text, sources = gather_context(args, e)
    session = Session.create(e, call_minutes, text, sources)
    _say(f"Session: {session.path.relative_to(e.path)}")

    previous = knowledge.previous_calls(e.slug)
    if previous["sessions"]:
        _say(f"Follow-up call: carrying over {len(previous['facts'])} fields and "
             f"{len(previous['questions'])} open questions from {len(previous['sessions'])} earlier call(s).")
        session.seed_from_previous(previous)

    status: dict = {}
    end_requested, quit_requested = threading.Event(), threading.Event()
    lrn = Learnings(e, cfg)
    engine = Engine(session, cfg, lrn, previous=previous)

    # Before the call: wiki learnings digest and the kickoff gap analysis run in parallel.
    def fetch_learnings():
        session.status["learnings"] = "fetching from the ShellKode wiki..."
        lrn.fetch(topics_for(e, text), text, log_path=session.ticks_dir / "learnings-kickoff.md")
        session.status.pop("learnings", None)
        status["wiki"] = "ok" if lrn.source == "wiki" else "sign-in needed (sow-live wiki-login)"

    learn_thread = threading.Thread(target=fetch_learnings, daemon=True)
    learn_thread.start()
    kickoff = threading.Thread(target=engine.tick, args=("kickoff",), daemon=True)
    kickoff.start()

    capture = None
    replay_done = threading.Event()
    if args.replay_transcript:
        threading.Thread(target=replay_transcript, args=(args.replay_transcript, session, args.speed, replay_done),
                         daemon=True).start()
    elif not args.no_audio:
        capture = Capture(cfg, session, status, lambda who, start, t: session.add_utterance(who, start, t))
        try:
            if args.replay_audio:
                capture.start_replay(args.replay_audio, realtime=not args.fast)
            else:
                capture.start_live()
        except RuntimeError as ex:
            status["asr"] = f"error: {ex}"
            _say(f"Audio/ASR unavailable: {ex}")

    def start_ticker():
        kickoff.join()
        engine.run_background()

    threading.Thread(target=start_ticker, daemon=True).start()

    if args.headless:
        seen = set()
        try:
            while True:
                time.sleep(2)
                for q in session.open_questions():
                    if q["id"] not in seen:
                        seen.add(q["id"])
                        print(f"[Q p{q.get('priority')}] {q['text']}", flush=True)
                for l in session.state["lookups"]:
                    if l["state"] == "done" and l["id"] not in seen:
                        seen.add(l["id"])
                        tag = "LEARN" if l["kind"] == "learnings_refresh" else (
                            "CACHED" if l.get("cached") else ("WIKI" if l["kind"] == "org_experience" else "AWS"))
                        print(f"[{tag}] {l.get('label') or l['query'][:90]}\n    -> {l['answer'].get('headline')}",
                              flush=True)
                for f in session.state["flags"]:
                    if f["id"] not in seen:
                        seen.add(f["id"])
                        print(f"[FLAG] {f['text']}", flush=True)
                if "learnings-done" not in seen and not learn_thread.is_alive():
                    seen.add("learnings-done")
                    print(f"[LEARNINGS] {lrn.status_line()}", flush=True)
                replay_finished = replay_done.is_set() or (
                    capture and args.replay_audio and not any(s.is_alive() for s in capture.sources))
                if (replay_finished and session.state["transcript_count"]
                        and engine.last_index >= session.state["transcript_count"]):
                    break
        except KeyboardInterrupt:
            pass
    else:
        from .panel import Panel_

        panel = Panel_(session, engine, status, on_end=end_requested.set, on_quit=quit_requested.set, title=e.title)
        try:
            panel.run()
        except KeyboardInterrupt:
            quit_requested.set()

    if capture:
        _say("Stopping audio and finishing transcription...")
        capture.stop(drain=True)
    engine.stop()
    learn_thread.join(timeout=5)

    if quit_requested.is_set():
        _say(f"Saved. Finalize later with: sow-live finalize {e.slug}")
        return 0
    return finalize(session, cfg, e, engine, interactive=interactive, handoff=not args.no_handoff)


# ------------------------------------------------------------------ engagement commands
def cmd_new(args) -> int:
    if not _require_setup():
        return 1
    existing = eng_mod.find(args.client)
    exact = [x for x in existing if eng_mod.norm(x.client) == eng_mod.norm(args.client)
             and eng_mod.norm(x.project) == eng_mod.norm(args.project or "")]
    if exact:
        _say(f"Already exists: {exact[0].path}")
        return 0
    e = eng_mod.create(args.client, args.project or "")
    _say(f"Created {e.path}")
    print(f"  Put this project's material in {e.sol}")
    print(f"  Before the discovery call: sow-live start --client \"{args.client}\"")
    return 0


def cmd_list(args) -> int:
    items = eng_mod.all_engagements()
    if not items:
        _say(f"No engagements yet in {Config.load().engagements_root}. Create one with: sow-live new \"Client\" \"Project\"")
        return 0
    rows = []
    for e in items:
        sess = e.sessions()
        last = sess[-1].name[:8] if sess else ""
        last = f"{last[6:8]}/{last[4:6]}/{last[:4]}" if last else "-"
        rows.append((e.slug, e.title, str(len(sess)), last, e.status()))
    w = [max(len(r[i]) for r in rows + [("Folder", "Engagement", "Calls", "Last call", "Status")]) for i in range(5)]
    header = ("Folder", "Engagement", "Calls", "Last call", "Status")
    print("  ".join(h.ljust(w[i]) for i, h in enumerate(header)))
    for r in rows:
        print("  ".join(c.ljust(w[i]) for i, c in enumerate(r)))
    return 0


def cmd_open(args) -> int:
    e = _engagement(args.name)
    if not e:
        return 1
    if shutil.which("kiro"):
        return subprocess.call(["kiro", str(e.path)])
    if Path("/Applications/Kiro.app").exists():
        return subprocess.call(["open", "-a", "Kiro", str(e.path)])
    _say(f"Kiro IDE not found. Engagement folder: {e.path}")
    return 1


def cmd_import(args) -> int:
    src = Path(args.folder).expanduser().resolve()
    if not (src / "sol").is_dir() and not (src / "build").is_dir():
        _say(f"{src} has no sol/ or build/ folder.")
        return 1
    e = eng_mod.import_folder(src, args.client, args.project or "")
    _say(f"Imported into {e.path}")
    return 0


def cmd_finalize(args) -> int:
    cfg = Config.load()
    if args.session and Path(args.session, "state.json").exists():
        path = Path(args.session)
        e = eng_mod.load(path.parent.parent)
    else:
        e = _engagement(args.session)
        if not e:
            return 1
        sess = e.sessions()
        if not sess:
            _say(f"No call sessions in {e.slug}.")
            return 1
        path = sess[-1]
    session = Session.load(path)
    _say(f"Finalizing {e.slug}/live/{path.name}")
    return finalize(session, cfg, e, interactive=_tty(), handoff=not args.no_handoff)


def cmd_generate(args) -> int:
    e = _engagement(args.name)
    return generate(Config.load(), e) if e else 1


def cmd_learnings(args) -> int:
    from . import context
    from .learnings import Learnings

    e = _engagement(args.name)
    if not e:
        return 1
    cfg = Config.load()
    text, _, _ = context.from_sol(e.sol)
    brief = e.build / "brief.md"
    if brief.exists():
        text += "\n" + brief.read_text()[:4000]
    lrn = Learnings(e, cfg)
    if args.reset:
        lrn.data = {"source": "none", "entries": [], "topics": [], "updated": "", "error": ""}
    _say("Searching the ShellKode wiki for relevant learnings (about a minute)...")
    lrn.fetch(args.topic or topics_for(e, text), text)
    _say(f"Learnings: {lrn.status_line()} -> {lrn.md_path}")
    if lrn.source != "wiki":
        _say(f"Wiki error: {lrn.data.get('error')}. Run: sow-live wiki-login")
        return 1
    return 0


# ------------------------------------------------------------------ setup commands
def cmd_init(args) -> int:
    from . import install

    return install.init(interactive=_tty() and not args.yes, force=args.force, check_only=args.check)


def cmd_auth(args) -> int:
    from . import install

    if args.remove:
        install.keychain_delete()
        _say("Removed the Kiro API key from the Keychain.")
        return 0
    if args.api_key_stdin:
        key = sys.stdin.read().strip()
    else:
        import getpass

        key = getpass.getpass("Kiro API key (hidden): ").strip()
    if not key:
        _say("No key entered.")
        return 1
    install.keychain_set(key)
    good, detail = install.headless_works()
    _say("Stored in the Keychain. Headless Kiro call works." if good else f"Stored, but the test call failed: {detail}")
    return 0 if good else 1


def cmd_uninstall(args) -> int:
    from . import install

    return install.uninstall(yes=args.yes)


def cmd_paths(args) -> int:
    cfg = Config.load()
    for k, v in (("version", __version__), ("home", SOW_HOME), ("settings", USER_CONFIG), ("framework", FRAMEWORK),
                 ("kiro", KIRO_HOME), ("engagements", cfg.engagements_root)):
        print(f"{k:12s} {v}")
    return 0


WIKI_PROBE = ("PROBE, not a customer question. Call the shellkode-wiki tool list_collections once. Reply with JSON only: "
              '{"ok": true if the call returned collections else false, "collections": <number of collections>, '
              '"error": "<exact error text if it failed, else empty>"}')


def wiki_probe(cfg: Config) -> tuple[bool, str]:
    from .kiro import KiroError, run_agent

    try:
        out = run_agent("sow-live-org", WIKI_PROBE, model=cfg["models"].get("org"), timeout=120, trust_tools=True)
    except KiroError as ex:
        return False, str(ex)
    if out.get("ok"):
        return True, f"{out.get('collections', '?')} collections visible"
    return False, out.get("error") or "wiki tools unavailable"


def cmd_wiki_login(args) -> int:
    cfg = Config.load()
    ok, msg = wiki_probe(cfg)
    if ok:
        _say(f"Wiki access works ({msg}).")
        return 0
    _say(f"Wiki not reachable from headless runs yet: {msg}")
    print("\nOpening Kiro CLI with the sow-live-org agent. Inside it:\n"
          "  1. type /mcp and press Enter\n"
          "  2. select shellkode-wiki and press Enter to sign in (Google SSO opens in your browser)\n"
          "  3. when it shows connected, type /quit\n"
          "Then run `sow-live wiki-login` again to confirm.\n")
    input("Press Enter to open Kiro CLI...")
    os.chdir(SOW_HOME)
    from .install import kiro_env

    os.execvpe("kiro-cli", ["kiro-cli", "chat", "--trust-workspace", "--agent", "sow-live-org"], kiro_env())
    return 0  # not reached


def cmd_wiki_seed(args) -> int:
    """Draft the framework's original seed learnings into the wiki (unpublished, for review)."""
    from .kiro import KiroError, run_agent

    cfg = Config.load()
    seed = framework_file("live", "seed-learnings.md").read_text()
    ok, msg = wiki_probe(cfg)
    if not ok:
        _say(f"Wiki not reachable: {msg}. Run: sow-live wiki-login")
        return 1
    if _tty() and input("Draft the 8 seed learnings into the wiki Inbox as unpublished drafts? [y/N] ").strip().lower() != "y":
        return 0
    _say("Checking the wiki for each learning and drafting the missing ones (a few minutes)...")
    try:
        out = run_agent("sow-live-wiki-writer", f"LEARNINGS TO MIGRATE:\n\n{seed}\n\nReply with the JSON object only.",
                        model=cfg["models"].get("org"), timeout=900, trust_tools=True,
                        log_path=SOW_HOME / "wiki-seed.log")
    except KiroError as ex:
        _say(f"Failed: {ex}")
        return 1
    for r in out.get("results", []):
        print(f"  {r.get('status', '?'):8s} {r.get('title', '')}  {r.get('url', '')}  {r.get('note', '')}")
    _say("Review and publish the drafts in the wiki. Nothing was published.")
    return 0


# ------------------------------------------------------------------ engine tools (called by the skills)
def cmd_docx(args) -> int:
    script = FRAMEWORK / "scripts" / "generate_sow_docx.py"
    return subprocess.call([sys.executable, str(script), args.content, *([args.output] if args.output else [])])


def cmd_diagram(args) -> int:
    return subprocess.call(["bash", str(FRAMEWORK / "scripts" / "export_diagram.sh"), args.input, args.output])


def cmd_preview(args) -> int:
    outdir = args.outdir or str(Path(args.docx).resolve().parent)
    return subprocess.call(["bash", str(FRAMEWORK / "scripts" / "preview_pdf.sh"), args.docx, outdir])


def cmd_mcp(args) -> int:
    from .mcp_server import serve

    return serve()


# ------------------------------------------------------------------ check
def cmd_check(args) -> int:
    """Audio levels for mic and system audio, one ASR round-trip, Kiro and wiki access."""
    import numpy as np

    from .audio import Segmenter, Source, WhisperServer
    from .install import headless_works

    cfg = Config.load()
    ok = True
    for tool in ("kiro-cli", "ffmpeg", "whisper-server"):
        found = shutil.which(tool)
        print(f"{'✓' if found else '✗'} {tool}: {found or 'missing'}")
        ok &= bool(found)
    for label, path in (("ASR model", cfg.asr_model), ("system-audio helper", SYSCAP_BIN), ("framework", FRAMEWORK)):
        print(f"{'✓' if path.exists() else '✗'} {label}: {path}")
        ok &= path.exists()
    if not ok:
        print("Run: sow-live init")
        return 1

    good, detail = headless_works()
    print(f"{'✓' if good else '✗'} Kiro headless call: {'ok' if good else detail}")
    ok &= good

    status: dict = {}
    got: dict[str, list] = {"SA": [], "Remote": []}
    srcs = []
    for who, cmd, fmt, rate in (
        ("SA", ["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
                "-i", f":{cfg['audio']['mic_device']}", "-ac", "1", "-ar", "16000", "-f", "s16le", "-"], "s16", 16000),
        ("Remote", [str(SYSCAP_BIN)], "f32", 48000),
    ):
        seg = Segmenter(cfg, lambda start, pcm, w=who: got[w].append(pcm), 0.0)
        src = Source(who, cmd, fmt, rate, seg, status)
        src.start()
        srcs.append((who, src))
    print("\nSpeak, and play some audio (e.g. a YouTube video) for 10 seconds...")
    peak = {w: 0.0 for w, _ in srcs}
    for _ in range(100):
        time.sleep(0.1)
        line = []
        for w, _ in srcs:
            lvl = status.get(f"{w}_level", 0.0)
            peak[w] = max(peak[w], lvl)
            line.append(f"{w}: {'█' * min(30, int(lvl * 300)):<30} {status.get(w, '')[:40]}")
        print("\r" + "   ".join(line), end="", flush=True)
    print()
    for _, s in srcs:
        s.stop()
    for w, s in srcs:
        s.seg.flush()
        st = status.get(w, "")
        if st.startswith(("ERROR", "error")):
            print(f"✗ {w}: {st}")
            if w == "Remote":
                print("  Grant Screen & System Audio Recording to this terminal app in System Settings >"
                      " Privacy & Security, then restart the terminal.")
            ok = False
        elif peak[w] < 0.004:
            print(f"✗ {w}: no signal (peak {peak[w]:.4f})")
            if w == "SA":
                print("  Grant Microphone access to this terminal app in System Settings > Privacy & Security.")
            ok = False
        else:
            print(f"✓ {w}: signal ok (peak {peak[w]:.3f}, {len(got[w])} speech segment(s))")

    asr = WhisperServer(cfg)
    asr.start()
    seg = next((got[w][0] for w in ("SA", "Remote") if got[w]), None)
    heard = asr.transcribe(seg if seg is not None else np.zeros(16000, dtype=np.int16))
    print(f"✓ ASR {'heard' if seg is not None else 'server up'}: {heard!r}")
    asr.stop()

    print("Checking ShellKode wiki access for the org agent...")
    wiki_ok, msg = wiki_probe(cfg)
    print(f"{'✓' if wiki_ok else '✗'} wiki: {msg}")
    if not wiki_ok:
        print("  Run: sow-live wiki-login")
        ok = False
    return 0 if ok else 1


# ------------------------------------------------------------------ main
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="sow-live", description="Discovery-call assist and SoW framework for ShellKode SAs.")
    p.add_argument("--version", action="version", version=f"sow-live {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="install tools, framework, model; set up auth (re-run to repair)")
    s.add_argument("--check", action="store_true", help="only report what is missing")
    s.add_argument("--force", action="store_true", help="overwrite skills/agents not installed by sow-live")
    s.add_argument("--yes", action="store_true", help="non-interactive, accept defaults")
    s.set_defaults(func=cmd_init)

    s = sub.add_parser("auth", help="store a Kiro API key in the macOS Keychain")
    s.add_argument("--api-key-stdin", action="store_true", help="read the key from stdin")
    s.add_argument("--remove", action="store_true", help="delete the stored key")
    s.set_defaults(func=cmd_auth)

    s = sub.add_parser("check", help="test microphone, system audio, ASR, Kiro and wiki access")
    s.set_defaults(func=cmd_check)

    s = sub.add_parser("wiki-login", help="sign in to the ShellKode wiki (once)")
    s.set_defaults(func=cmd_wiki_login)

    s = sub.add_parser("wiki-seed", help="draft the framework's seed learnings into the wiki (for review)")
    s.set_defaults(func=cmd_wiki_seed)

    s = sub.add_parser("new", help="create an engagement folder")
    s.add_argument("client")
    s.add_argument("project", nargs="?", default="")
    s.set_defaults(func=cmd_new)

    s = sub.add_parser("list", help="list engagements")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("open", help="open an engagement in Kiro IDE")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_open)

    s = sub.add_parser("import", help="import an old single-project framework folder (sol/, build/)")
    s.add_argument("folder")
    s.add_argument("--client", required=True)
    s.add_argument("--project", default="")
    s.set_defaults(func=cmd_import)

    s = sub.add_parser("start", help="start the call assist (run ~5 minutes before the call)")
    s.add_argument("--client", help="customer name (finds or creates the engagement)")
    s.add_argument("--minutes", type=int, help="planned call length")
    s.add_argument("--context", help="pre-call context as text (instead of sol/)")
    s.add_argument("--context-file", help="pre-call context file (instead of sol/)")
    s.add_argument("--model", help="override the live model")
    s.add_argument("--no-audio", action="store_true", help="no capture; notes and lookups only")
    s.add_argument("--replay-audio", metavar="FILE", help="test: feed a recorded call instead of live audio")
    s.add_argument("--fast", action="store_true", help="with --replay-audio: do not wait in real time")
    s.add_argument("--replay-transcript", metavar="FILE", help="test: feed '[mm:ss] Speaker: text' lines")
    s.add_argument("--speed", type=float, default=1.0, help="with --replay-transcript: time multiplier")
    s.add_argument("--headless", action="store_true", help="no panel; print events")
    s.add_argument("--no-handoff", action="store_true", help="write the brief but do not start the SoW pipeline")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("finalize", help="re-run the post-call step (latest session of an engagement)")
    s.add_argument("session", nargs="?", help="engagement name or session folder")
    s.add_argument("--no-handoff", action="store_true")
    s.set_defaults(func=cmd_finalize)

    s = sub.add_parser("generate", help="generate the SoW for an engagement")
    s.add_argument("name", nargs="?")
    s.set_defaults(func=cmd_generate)

    s = sub.add_parser("learnings", help="refresh an engagement's learnings digest from the wiki")
    s.add_argument("name", nargs="?")
    s.add_argument("--topic", help="search this topic instead of the engagement context")
    s.add_argument("--reset", action="store_true", help="rebuild the digest from scratch")
    s.set_defaults(func=cmd_learnings)

    s = sub.add_parser("docx", help="render content JSON to the branded .docx (used by the skills)")
    s.add_argument("content")
    s.add_argument("output", nargs="?")
    s.set_defaults(func=cmd_docx)

    s = sub.add_parser("diagram", help="export .drawio to PNG (used by the skills)")
    s.add_argument("input")
    s.add_argument("output")
    s.set_defaults(func=cmd_diagram)

    s = sub.add_parser("preview", help="render a .docx to PDF (used by the skills)")
    s.add_argument("docx")
    s.add_argument("outdir", nargs="?")
    s.set_defaults(func=cmd_preview)

    s = sub.add_parser("mcp", help="run the personal knowledge-graph MCP server (stdio)")
    s.set_defaults(func=cmd_mcp)

    s = sub.add_parser("paths", help="show where sow-live keeps things")
    s.set_defaults(func=cmd_paths)

    s = sub.add_parser("uninstall", help="remove installed skills/agents and data (engagements are kept)")
    s.add_argument("--yes", action="store_true")
    s.set_defaults(func=cmd_uninstall)
    return p


def main(argv=None) -> int:
    import signal

    signal.signal(signal.SIGPIPE, signal.SIG_DFL)  # exit quietly when piped into head etc.
    args = build_parser().parse_args(argv)
    if args.cmd not in ("init", "uninstall", "mcp", "paths"):
        from .install import auto_sync

        auto_sync()
    return args.func(args)
