"""Engagement folders: one per customer project, under engagements_root (~/SoW).

  <root>/<client>-<project>/
    engagement.json      client, project, aliases, created
    sol/                 that project's material only
    build/               brief.md, learnings.md, scratchpads, diagram, .docx
    live/<session>/      discovery-call sessions
    .kiro/               MCP config (AWS servers + personal knowledge graph) and IDE hooks
"""

from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path

from .config import DATA, Config, framework_file
from .install import render

MARKER = "engagement.json"
SUFFIXES = r"\b(pvt|private|ltd|limited|llp|inc|corp|corporation|co|company|plc|gmbh|llc|technologies|tech)\b\.?"


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:48] or "engagement"


def norm(text: str) -> str:
    t = re.sub(SUFFIXES, " ", text.lower())
    return re.sub(r"[^a-z0-9]+", "", t)


@dataclass
class Engagement:
    path: Path
    meta: dict

    @property
    def slug(self) -> str:
        return self.path.name

    @property
    def client(self) -> str:
        return self.meta.get("client", self.slug)

    @property
    def project(self) -> str:
        return self.meta.get("project", "")

    @property
    def title(self) -> str:
        return f"{self.client}: {self.project}" if self.project else self.client

    sol = property(lambda self: self.path / "sol")
    build = property(lambda self: self.path / "build")
    live = property(lambda self: self.path / "live")

    def sessions(self) -> list[Path]:
        if not self.live.exists():
            return []
        return sorted(p for p in self.live.iterdir() if (p / "state.json").exists())

    def status(self) -> str:
        docs = sorted(self.build.glob("*.docx"), key=lambda p: p.stat().st_mtime) if self.build.exists() else []
        if docs:
            return f"SoW generated {datetime.fromtimestamp(docs[-1].stat().st_mtime):%d %b}"
        brief = self.build / "brief.md"
        if brief.exists():
            return "brief ready" if "<!-- source: sow-live -->" in brief.read_text() else "brief (manual)"
        return "no brief yet"

    def save(self) -> None:
        (self.path / MARKER).write_text(json.dumps(self.meta, indent=2, ensure_ascii=False) + "\n")

    def ensure_scaffold(self) -> None:
        """Create missing folders and refresh the sow-live managed .kiro files."""
        for d in (self.sol, self.build, self.live):
            d.mkdir(parents=True, exist_ok=True)
        readme = self.sol / "README.md"
        if not readme.exists():
            readme.write_text(framework_file("engagement", "sol-README.md").read_text())
        src_root = DATA / "framework" / "engagement" / ".kiro"
        for src in src_root.rglob("*"):
            if src.is_file():
                dest = self.path / ".kiro" / src.relative_to(src_root)
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = render(src, src.read_bytes())
                if not dest.exists() or dest.read_bytes() != data:
                    dest.write_bytes(data)


def root(cfg: Config | None = None) -> Path:
    r = (cfg or Config.load()).engagements_root
    r.mkdir(parents=True, exist_ok=True)
    return r


def load(path: Path) -> Engagement | None:
    m = path / MARKER
    if not m.exists():
        return None
    return Engagement(path, json.loads(m.read_text()))


def all_engagements(cfg: Config | None = None) -> list[Engagement]:
    out = []
    for p in sorted(root(cfg).iterdir()):
        if p.is_dir():
            e = load(p)
            if e:
                out.append(e)
    return out


def from_cwd() -> Engagement | None:
    p = Path.cwd().resolve()
    for cand in (p, *p.parents):
        e = load(cand)
        if e:
            return e
    return None


def create(client: str, project: str, cfg: Config | None = None) -> Engagement:
    short = re.sub(SUFFIXES, " ", client, flags=re.I).strip() or client
    base = slugify(short) + (f"-{slugify(project)}" if project else "")
    path = root(cfg) / base
    n = 2
    while path.exists():
        path = root(cfg) / f"{base}-{n}"
        n += 1
    path.mkdir(parents=True)
    e = Engagement(path, {"client": client, "project": project, "aliases": [],
                          "created": datetime.now().isoformat(timespec="seconds")})
    e.save()
    e.ensure_scaffold()
    return e


def find(query: str, cfg: Config | None = None) -> list[Engagement]:
    """Engagements matching a client/project/slug query, best first."""
    q = norm(query)
    if not q:
        return []
    scored = []
    for e in all_engagements(cfg):
        names = [e.client, e.slug, *e.meta.get("aliases", [])]
        keys = [norm(n) for n in names] + [norm(f"{e.client} {e.project}")]
        if q in keys:
            score = 1.0
        elif any(k.startswith(q) or q.startswith(k) for k in keys if k):
            score = 0.9
        elif any(q in k for k in keys if k):
            score = 0.8
        else:
            score = max(SequenceMatcher(None, q, k).ratio() for k in keys if k)
        if score >= 0.72:
            scored.append((score, e))
    scored.sort(key=lambda t: (-t[0], t[1].slug))
    return [e for _, e in scored]


def resolve(query: str | None, *, interactive: bool, create_if_missing: bool = False,
            client_for_create: str | None = None, cfg: Config | None = None) -> Engagement | None:
    """Find the engagement the user means, asking when it's ambiguous."""
    if not query:
        e = from_cwd()
        if e:
            return e
        if not interactive:
            return None
        query = input("Client name: ").strip()
    matches = find(query, cfg)
    if len(matches) == 1:
        e = matches[0]
        if not interactive or norm(query) in (norm(e.client), norm(e.slug)):
            return e
        ans = input(f"Use engagement '{e.title}' ({e.slug})? [Y/n] ").strip().lower()
        if ans in ("", "y", "yes"):
            if norm(query) != norm(e.client) and query not in e.meta.get("aliases", []):
                e.meta.setdefault("aliases", []).append(query)
                e.save()
            return e
    elif len(matches) > 1:
        if not interactive:
            return matches[0] if norm(query) == norm(matches[0].client) else None
        print("Several engagements match:")
        for i, e in enumerate(matches, 1):
            print(f"  {i}) {e.title}  [{e.slug}]  {len(e.sessions())} call(s), {e.status()}")
        print("  n) new engagement")
        ans = input("Choose: ").strip().lower()
        if ans.isdigit() and 1 <= int(ans) <= len(matches):
            return matches[int(ans) - 1]
        if ans != "n":
            return None
    if not create_if_missing:
        return None
    client = client_for_create or query
    if interactive:
        if input(f"No engagement for '{client}'. Create one? [Y/n] ").strip().lower() not in ("", "y", "yes"):
            return None
        project = input("Project title (e.g. Support assistant): ").strip()
    else:
        project = ""
    return create(client, project, cfg)


def import_folder(src: Path, client: str, project: str, cfg: Config | None = None) -> Engagement:
    """Copy an old single-project framework checkout (sol/, build/) into a new engagement."""
    e = create(client, project, cfg)
    if (src / "sol").is_dir():
        for f in (src / "sol").iterdir():
            if f.name == "README.md":
                continue
            dest = e.sol / f.name
            shutil.copytree(f, dest) if f.is_dir() else shutil.copy2(f, dest)
    if (src / "build").is_dir():
        for f in (src / "build").iterdir():
            if f.name in ("bin",):
                continue
            if f.name == "live" and f.is_dir():
                for s in f.iterdir():
                    if (s / "state.json").exists():
                        shutil.copytree(s, e.live / s.name)
                continue
            dest = e.build / f.name
            shutil.copytree(f, dest) if f.is_dir() else shutil.copy2(f, dest)
    return e
