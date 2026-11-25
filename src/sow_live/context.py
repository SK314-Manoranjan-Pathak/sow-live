"""Gather pre-call context: whatever is in sol/, or what the SA types."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


TEXT_EXT = {".md", ".txt", ".csv", ".json", ".yaml", ".yml", ".eml", ".html", ".vtt", ".srt"}
MAX_CHARS_PER_FILE = 15_000
MAX_TOTAL = 60_000


def _read(path: Path) -> str | None:
    ext = path.suffix.lower()
    try:
        if ext in TEXT_EXT:
            return path.read_text(errors="ignore")
        if ext == ".docx":
            from docx import Document  # python-docx is already a framework dependency
            d = Document(str(path))
            parts = [p.text for p in d.paragraphs if p.text.strip()]
            for t in d.tables:
                for row in t.rows:
                    parts.append(" | ".join(c.text.strip() for c in row.cells))
            return "\n".join(parts)
        if ext == ".pdf" and shutil.which("pdftotext"):
            return subprocess.run(["pdftotext", "-layout", str(path), "-"], capture_output=True,
                                  text=True, timeout=60).stdout
    except Exception as e:  # unreadable file: note it, keep going
        return f"(could not read: {e})"
    return None


def from_sol(root: Path) -> tuple[str, list[str], list[str]]:
    """Returns (context text, files used, files skipped)."""
    used, skipped, chunks, total = [], [], [], 0
    if not root.exists():
        return "", used, skipped
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.name.startswith(".") or (p.parent == root and p.name == "README.md"):
            continue
        text = _read(p)
        rel = str(p.relative_to(root.parent))
        if not text or not text.strip():
            skipped.append(rel)
            continue
        text = text.strip()[:MAX_CHARS_PER_FILE]
        if total + len(text) > MAX_TOTAL:
            skipped.append(f"{rel} (context limit)")
            continue
        chunks.append(f"### {rel}\n{text}")
        used.append(rel)
        total += len(text)
    return "\n\n".join(chunks), used, skipped


def prompt_typed() -> str:
    print("\nNo usable notes in sol/. Type or paste what you know about the use case so far.")
    print("Finish with an empty line followed by Ctrl-D (or just Ctrl-D to start with no context).\n")
    try:
        return sys.stdin.read().strip()
    except KeyboardInterrupt:
        return ""
