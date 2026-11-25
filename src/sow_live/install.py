"""`sow-live init`, framework sync, upgrade and uninstall.

Everything sow-live writes under ~/.kiro is recorded in ~/.sow-live/manifest.json
with its hash, so upgrades replace only our files and uninstall removes exactly
those. Files we did not install are never overwritten.
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

from . import __version__
from .config import (BIN_DIR, DATA, FRAMEWORK, KIRO_AGENTS, KIRO_HOME, KIRO_SKILLS, MANIFEST, MODELS_DIR, SOW_HOME,
                     SYSCAP_BIN, USER_CONFIG, Config, read_user_config, write_user_config)

TEXT_SUFFIXES = {".md", ".json", ".hook", ".sh", ".txt", ".toml", ".yaml", ".yml"}
KEYCHAIN_SERVICE = "sow-live-kiro-api-key"
BREW_PATHS = ("/opt/homebrew/bin", "/usr/local/bin")

FORMULAS = ["whisper-cpp", "ffmpeg", "uv", "node", "poppler"]
CASKS = {"drawio": "/Applications/draw.io.app", "libreoffice": "/Applications/LibreOffice.app"}


def say(msg: str) -> None:
    print(f"\033[36m==>\033[0m {msg}", flush=True)


def warn(msg: str) -> None:
    print(f"\033[33m!!\033[0m {msg}", flush=True)


def ok(msg: str) -> None:
    print(f"\033[32m✓\033[0m {msg}", flush=True)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sow_live_bin() -> str:
    found = shutil.which("sow-live")
    if found:
        return str(Path(found).resolve()) if not Path(found).is_symlink() else found
    return str(Path(sys.argv[0]).resolve())


def tokens() -> dict[str, str]:
    return {
        "@SOW_FRAMEWORK@": str(FRAMEWORK),
        "@KIRO_SKILLS@": str(KIRO_SKILLS),
        "@SOW_HOME@": str(SOW_HOME),
        "@SOW_LIVE_BIN@": sow_live_bin(),
    }


def render(path: Path, data: bytes) -> bytes:
    if path.suffix not in TEXT_SUFFIXES:
        return data
    text = data.decode("utf-8")
    for k, v in tokens().items():
        text = text.replace(k, v)
    return text.encode("utf-8")


def render_agent(path: Path, data: bytes) -> bytes:
    """Kiro CLI V3 rejects absolute file:// prompts, so inline the prompt text."""
    cfg = json.loads(render(path, data))
    prompt = cfg.get("prompt", "")
    if prompt.startswith("file://"):
        rel = prompt[len("file://"):]
        name = Path(rel).name
        cfg["prompt"] = (DATA / "framework" / "prompts" / name).read_text()
    return (json.dumps(cfg, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


# ------------------------------------------------------------------ dependencies
def _run(cmd, **kw) -> int:
    print(f"   $ {cmd if isinstance(cmd, str) else ' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, shell=isinstance(cmd, str), **kw)


def _ensure_brew_on_path() -> None:
    for p in BREW_PATHS:
        if Path(p, "brew").exists() and p not in os.environ["PATH"].split(":"):
            os.environ["PATH"] = f"{p}:{os.environ['PATH']}"


def _has_clt() -> bool:
    return subprocess.run(["xcode-select", "-p"], capture_output=True).returncode == 0


def dependency_plan() -> list[tuple[str, bool]]:
    _ensure_brew_on_path()
    plan = [("Xcode Command Line Tools", _has_clt()), ("Homebrew", bool(shutil.which("brew")))]
    brew_list = set()
    if shutil.which("brew"):
        out = subprocess.run(["brew", "list", "--formula", "-1"], capture_output=True, text=True).stdout
        brew_list = set(out.split())
    for f in FORMULAS:
        binary = {"whisper-cpp": "whisper-server", "poppler": "pdftotext"}.get(f, f)
        plan.append((f, f in brew_list or bool(shutil.which(binary))))
    for cask, app in CASKS.items():
        plan.append((cask, Path(app).exists()))
    plan.append(("kiro-cli", bool(shutil.which("kiro-cli"))))
    return plan


def install_dependencies(check_only: bool = False) -> bool:
    plan = dependency_plan()
    missing = [name for name, present in plan if not present]
    for name, present in plan:
        (ok if present else warn)(f"{name}: {'installed' if present else 'missing'}")
    if not missing:
        return True
    if check_only:
        return False

    if "Xcode Command Line Tools" in missing:
        say("Installing Xcode Command Line Tools. A macOS dialog opens: click Install and wait for it to finish.")
        subprocess.call(["xcode-select", "--install"])
        deadline = time.time() + 45 * 60
        while not _has_clt():
            if time.time() > deadline:
                warn("Timed out waiting for Xcode Command Line Tools.")
                return False
            time.sleep(10)
        ok("Xcode Command Line Tools installed")

    if "Homebrew" in missing:
        say("Installing Homebrew (asks for your Mac password once)")
        rc = _run('/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"')
        _ensure_brew_on_path()
        if rc != 0 or not shutil.which("brew"):
            warn("Homebrew install failed. Install it from https://brew.sh and re-run `sow-live init`.")
            return False

    failed = []
    for f in FORMULAS:
        if f in missing and _run(["brew", "install", f]) != 0:
            failed.append(f)
    for cask in CASKS:
        if cask in missing and _run(["brew", "install", "--cask", cask]) != 0:
            failed.append(cask)
    if "kiro-cli" in missing:
        say("Installing Kiro CLI")
        if _run("curl -fsSL https://cli.kiro.dev/install | bash") != 0:
            failed.append("kiro-cli")
        local_bin = str(Path("~/.local/bin").expanduser())
        if local_bin not in os.environ["PATH"].split(":"):
            os.environ["PATH"] = f"{local_bin}:{os.environ['PATH']}"
    if failed:
        warn(f"Could not install: {', '.join(failed)}. Fix the error above and re-run `sow-live init`.")
        return False
    return True


# ------------------------------------------------------------------ Kiro auth
def keychain_get() -> str | None:
    r = subprocess.run(["security", "find-generic-password", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE, "-w"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return r.stdout.strip() or None


def keychain_set(key: str) -> None:
    subprocess.run(["security", "add-generic-password", "-U", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE,
                    "-w", key], check=True, capture_output=True)


def keychain_delete() -> None:
    subprocess.run(["security", "delete-generic-password", "-a", getpass.getuser(), "-s", KEYCHAIN_SERVICE],
                   capture_output=True)


def kiro_env() -> dict:
    env = dict(os.environ)
    if not env.get("KIRO_API_KEY"):
        key = keychain_get()
        if key:
            env["KIRO_API_KEY"] = key
    return env


def kiro_logged_in() -> bool:
    if not shutil.which("kiro-cli"):
        return False
    r = subprocess.run(["kiro-cli", "whoami"], capture_output=True, text=True, env=kiro_env())
    return r.returncode == 0 and "not logged in" not in (r.stdout + r.stderr).lower()


def headless_works() -> tuple[bool, str]:
    r = subprocess.run(["kiro-cli", "chat", "--no-interactive", "--trust-tools=", "--model", "claude-haiku-5.5",
                        "Reply with exactly: OK"], capture_output=True, text=True, env=kiro_env(), timeout=180,
                       cwd=str(SOW_HOME))
    out = (r.stdout or "").strip()
    return ("OK" in out), (out or r.stderr.strip())[-200:]


def setup_auth(interactive: bool) -> bool:
    if keychain_get():
        ok("Kiro API key found in Keychain")
    elif kiro_logged_in():
        ok("Kiro CLI is logged in (headless runs use your login)")
    elif interactive:
        say("Kiro CLI is not logged in. Choose one:")
        print("   1) Paste a Kiro API key (kiro.dev account settings; needs a Pro plan or above)")
        print("   2) Log in with your browser (kiro-cli login)")
        choice = input("   [1/2]: ").strip()
        if choice == "1":
            key = getpass.getpass("   Kiro API key (hidden): ").strip()
            if not key:
                warn("No key entered.")
                return False
            keychain_set(key)
            ok("Stored in the macOS Keychain (service: sow-live-kiro-api-key)")
        else:
            subprocess.call(["kiro-cli", "login"])
    else:
        warn("Kiro CLI is not logged in and no API key is stored. Run `sow-live auth`.")
        return False
    good, detail = headless_works()
    (ok if good else warn)("Headless Kiro call works" if good else f"Headless Kiro call failed: {detail}")
    return good


# ------------------------------------------------------------------ model + helper
def download_model(cfg: Config) -> bool:
    target = cfg.asr_model
    if target.exists() and target.stat().st_size > 1_000_000:
        ok(f"Whisper model present: {target}")
        return True
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    url = cfg["asr"]["model_url"]
    say(f"Downloading Whisper model ({target.name}, about 550 MB)")
    part = target.with_suffix(".part")
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(part, "wb") as f:
            total = int(r.headers.get("Content-Length", 0))
            done, shown = 0, -1
            step = 1 if sys.stdout.isatty() else 25
            while chunk := r.read(1 << 20):
                f.write(chunk)
                h.update(chunk)
                done += len(chunk)
                pct = done * 100 // total if total else 0
                if total and pct // step != shown:
                    shown = pct // step
                    end = "" if sys.stdout.isatty() else "\n"
                    print(f"\r   {pct:3d}%  {done >> 20} / {total >> 20} MB", end=end, flush=True)
        print()
    except Exception as e:  # network errors
        warn(f"Download failed: {e}")
        part.unlink(missing_ok=True)
        return False
    expected = cfg["asr"].get("model_sha256")
    if expected and h.hexdigest() != expected:
        warn("Model checksum mismatch; deleted the download.")
        part.unlink(missing_ok=True)
        return False
    part.replace(target)
    ok("Whisper model downloaded")
    return True


def build_syscap() -> bool:
    src = FRAMEWORK / "live" / "syscap.swift"
    if not src.exists():
        src = DATA / "framework" / "live" / "syscap.swift"
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    stamp = BIN_DIR / ".syscap.sha"
    digest = _sha(src.read_bytes())
    if SYSCAP_BIN.exists() and stamp.exists() and stamp.read_text() == digest:
        ok("System-audio helper up to date")
        return True
    say("Compiling the system-audio helper (ScreenCaptureKit)")
    r = subprocess.run(["swiftc", "-O", "-o", str(SYSCAP_BIN), str(src)], capture_output=True, text=True)
    if r.returncode != 0:
        warn(f"swiftc failed:\n{r.stderr[-1500:]}")
        return False
    stamp.write_text(digest)
    ok(f"Built {SYSCAP_BIN}")
    return True


# ------------------------------------------------------------------ framework sync
def _load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"version": None, "files": {}}


def _save_manifest(m: dict) -> None:
    SOW_HOME.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2))


def _kiro_targets() -> dict[Path, Path]:
    """Map of package source file -> target under ~/.kiro."""
    out: dict[Path, Path] = {}
    for skill in sorted((DATA / "skills").iterdir()):
        if skill.is_dir():
            for f in skill.rglob("*"):
                if f.is_file() and f.name != ".DS_Store":
                    out[f] = KIRO_SKILLS / skill.name / f.relative_to(skill)
    for f in sorted((DATA / "agents").glob("*.json")):
        out[f] = KIRO_AGENTS / f.name
    return out


def sync_framework(force: bool = False, quiet: bool = False) -> list[str]:
    """Install/upgrade the framework. Returns warnings."""
    log = (lambda *_: None) if quiet else say
    warnings: list[str] = []

    # 1. ~/.sow-live/framework is entirely ours: replace it.
    tmp = SOW_HOME / ".framework.new"
    if tmp.exists():
        shutil.rmtree(tmp)
    src_root = DATA / "framework"
    for f in src_root.rglob("*"):
        if f.is_file() and f.name != ".DS_Store":
            dest = tmp / f.relative_to(src_root)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(render(f, f.read_bytes()))
            if f.suffix == ".sh":
                dest.chmod(0o755)
    if FRAMEWORK.exists():
        shutil.rmtree(FRAMEWORK)
    tmp.replace(FRAMEWORK)
    log(f"Framework installed at {FRAMEWORK}")

    # 2. Skills and agents under ~/.kiro, tracked in the manifest.
    manifest = _load_manifest()
    old_files: dict = manifest.get("files", {})
    new_files: dict = {}
    skipped_skills: set[str] = set()
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")

    targets = _kiro_targets()
    # A skill we didn't install that already exists (e.g. wiki-assistant installed by hand) is left alone.
    if not force:
        for skill in (DATA / "skills").iterdir():
            skill_md = KIRO_SKILLS / skill.name / "SKILL.md"
            if skill_md.exists() and str(skill_md) not in old_files:
                ours = render(skill_md, (skill / "SKILL.md").read_bytes())
                if skill_md.read_bytes() != ours:
                    skipped_skills.add(skill.name)

    for src, dest in targets.items():
        rel_skill = dest.relative_to(KIRO_SKILLS).parts[0] if KIRO_SKILLS in dest.parents else None
        if rel_skill in skipped_skills:
            continue
        data = render_agent(src, src.read_bytes()) if dest.parent == KIRO_AGENTS else render(src, src.read_bytes())
        key = str(dest)
        if dest.exists():
            current = dest.read_bytes()
            if key in old_files:
                if _sha(current) != old_files[key] and current != data:
                    backup = dest.with_name(f"{dest.name}.bak-{stamp}")
                    shutil.copy2(dest, backup)
                    warnings.append(f"You had edited {dest}; saved your version as {backup.name}")
            elif current != data and not force:
                warnings.append(f"Not overwriting {dest} (not installed by sow-live). Use `sow-live init --force`.")
                continue
            elif current != data:
                backup = dest.with_name(f"{dest.name}.bak-{stamp}")
                shutil.copy2(dest, backup)
                warnings.append(f"Replaced {dest}; your version is in {backup.name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        new_files[key] = _sha(data)

    for name in sorted(skipped_skills):
        warnings.append(f"Kept your existing `{name}` skill in {KIRO_SKILLS / name} (not installed by sow-live).")

    # 3. Remove files we installed before but no longer ship.
    for key in set(old_files) - set(new_files):
        p = Path(key)
        if p.exists() and _sha(p.read_bytes()) == old_files[key]:
            p.unlink()
            _prune(p.parent)

    manifest = {"version": __version__, "installed_at": datetime.now().isoformat(timespec="seconds"),
                "files": new_files}
    _save_manifest(manifest)
    perm_warning = install_permissions()
    if perm_warning:
        warnings.append(perm_warning)
    log(f"Installed {len(new_files)} files into {KIRO_HOME} (skills + agents)")
    return warnings


PERM_FILE = KIRO_HOME / "settings" / "permissions.yaml"
PERM_BEGIN = "  # >>> sow-live (managed; removed by `sow-live uninstall`)"
PERM_END = "  # <<< sow-live"


def _perm_block() -> str:
    skills = sorted(p.name for p in (DATA / "skills").iterdir() if p.is_dir())
    reads = [f"{KIRO_SKILLS}/{s}/**" for s in skills] + [f"{FRAMEWORK}/**"]
    lines = [PERM_BEGIN, "  - capability: fs_read", "    effect: allow", "    match:"]
    lines += [f'      - "{r}"' for r in reads]
    lines += ["  - capability: shell", "    effect: allow", "    match:",
              '      - "sow-live docx *"', '      - "sow-live diagram *"', '      - "sow-live preview *"', PERM_END]
    return "\n".join(lines) + "\n"


def _strip_perm_block(text: str) -> str:
    if PERM_BEGIN not in text:
        return text
    head, rest = text.split(PERM_BEGIN, 1)
    tail = rest.split(PERM_END, 1)[1] if PERM_END in rest else ""
    return head.rstrip("\n") + "\n" + tail.lstrip("\n")


def install_permissions() -> str | None:
    """Let the SoW pipeline read the installed framework without a prompt per file. Returns a warning or None."""
    PERM_FILE.parent.mkdir(parents=True, exist_ok=True)
    text = PERM_FILE.read_text() if PERM_FILE.exists() else "rules:\n"
    text = _strip_perm_block(text)
    top_keys = [ln.split(":")[0] for ln in text.splitlines() if ln and not ln[0].isspace() and not ln.startswith("#")]
    if top_keys and top_keys[-1] != "rules":
        return (f"Could not add read permissions to {PERM_FILE} automatically (its `rules:` list isn't last). "
                f"Add this under `rules:` yourself:\n{_perm_block()}")
    if not top_keys:
        text = "rules:\n"
    PERM_FILE.write_text(text.rstrip("\n") + "\n" + _perm_block())
    return None


def remove_permissions() -> None:
    if PERM_FILE.exists():
        PERM_FILE.write_text(_strip_perm_block(PERM_FILE.read_text()))


def _prune(d: Path) -> None:
    while d not in (KIRO_SKILLS, KIRO_AGENTS, KIRO_HOME) and d.exists() and not any(d.iterdir()):
        d.rmdir()
        d = d.parent


def needs_sync() -> bool:
    return _load_manifest().get("version") != __version__


def auto_sync() -> None:
    """Called on every command: refresh installed files after a package upgrade."""
    if MANIFEST.exists() and needs_sync():
        for w in sync_framework(quiet=True):
            warn(w)
        ok(f"sow-live upgraded to {__version__}; framework files refreshed.")


def uninstall(yes: bool = False) -> int:
    m = _load_manifest()
    removed = 0
    for key, sha in m.get("files", {}).items():
        p = Path(key)
        if p.exists():
            if _sha(p.read_bytes()) != sha:
                warn(f"Keeping {p}: it was edited after install.")
                continue
            p.unlink()
            removed += 1
            _prune(p.parent)
    ok(f"Removed {removed} files from {KIRO_HOME}")
    remove_permissions()
    if FRAMEWORK.exists():
        shutil.rmtree(FRAMEWORK)
    MANIFEST.unlink(missing_ok=True)
    keep = "y"
    if not yes:
        keep = input(f"Delete {SOW_HOME} (models, knowledge graph, settings)? Your engagement folders are kept. [y/N] ")
    if keep.strip().lower() == "y":
        shutil.rmtree(SOW_HOME, ignore_errors=True)
        ok(f"Deleted {SOW_HOME}")
    if keychain_get():
        if yes or input("Remove the Kiro API key from the Keychain? [y/N] ").strip().lower() == "y":
            keychain_delete()
    print("Finally: uv tool uninstall sow-live")
    return 0


# ------------------------------------------------------------------ init
def configure(interactive: bool) -> None:
    cur = read_user_config()
    cfg = Config.load()
    updates = {}
    if interactive:
        root = input(f"Engagements folder [{cur.get('engagements_root', cfg['engagements_root'])}]: ").strip()
        if root:
            updates["engagements_root"] = root
        author = input(f"Your name (SoW author) [{cur.get('author', '')}]: ").strip()
        if author:
            updates["author"] = author
        lang = input(f"Call language: en, or auto for mixed Hindi/English [{cfg['asr']['language']}]: ").strip()
        if lang:
            updates["asr"] = {"language": lang}
    if updates or not USER_CONFIG.exists():
        write_user_config(updates)
    Config.load().engagements_root.mkdir(parents=True, exist_ok=True)
    ok(f"Settings: {USER_CONFIG}")


def init(interactive: bool = True, force: bool = False, check_only: bool = False) -> int:
    SOW_HOME.mkdir(parents=True, exist_ok=True)
    print(f"sow-live {__version__} setup\n")

    say("1/6 System tools")
    if not install_dependencies(check_only=check_only):
        if check_only:
            print("\nRun `sow-live init` (without --check) to install the missing tools.")
        return 1
    if check_only:
        return 0

    say("2/6 Framework (skills and agents into ~/.kiro)")
    for w in sync_framework(force=force):
        warn(w)

    say("3/6 Settings")
    configure(interactive)
    cfg = Config.load()

    say("4/6 Kiro authentication")
    auth_ok = setup_auth(interactive)

    say("5/6 Speech recognition")
    model_ok = download_model(cfg)
    helper_ok = build_syscap()

    say("6/6 Permissions and wiki")
    print("   Grant these to the terminal app you run sow-live in, under System Settings > Privacy & Security:\n"
          "     - Microphone\n"
          "     - Screen & System Audio Recording\n"
          "   Restart the terminal after granting them, then run `sow-live check`.\n"
          "   The ShellKode wiki needs a one-time sign-in: `sow-live wiki-login`.")
    local_bin = str(Path("~/.local/bin").expanduser())
    if local_bin not in os.environ.get("PATH", "").split(":"):
        warn(f"{local_bin} is not on your PATH. Run `uv tool update-shell` and open a new terminal.")

    print()
    if auth_ok and model_ok and helper_ok:
        ok("Setup complete. Next: sow-live check, then sow-live wiki-login")
        return 0
    warn("Setup finished with problems (see above). Re-run `sow-live init` after fixing them.")
    return 1
