"""Headless Kiro CLI calls that return a JSON object."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

from .config import SOW_HOME

ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


class KiroError(RuntimeError):
    pass


def extract_json(text: str) -> dict:
    """Pull the last top-level JSON object out of the agent's reply."""
    text = ANSI.sub("", text)
    fence = re.findall(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidates = fence[::-1] if fence else []
    # Fallback: scan for balanced objects from the end.
    if not candidates:
        starts = [m.start() for m in re.finditer(r"\{", text)]
        for s in starts:
            depth, in_str, esc = 0, False, False
            for i in range(s, len(text)):
                c = text[i]
                if in_str:
                    esc = (c == "\\") and not esc
                    if c == '"' and not esc:
                        in_str = False
                    elif c != "\\":
                        esc = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[s : i + 1])
                        break
            if candidates:
                break
    for c in candidates:
        try:
            obj = json.loads(c)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            continue
    raise KiroError("no JSON object in agent reply")


def run_agent(agent: str, prompt: str, *, model: str | None, timeout: int, log_path: Path | None = None,
              trust_tools: bool = False) -> dict:
    cmd = ["kiro-cli", "chat", "--no-interactive", "--trust-workspace", "--agent", agent]
    if model:
        cmd += ["--model", model]
    cmd += ["--trust-all-tools"] if trust_tools else ["--trust-tools="]
    t0 = time.time()
    try:
        from .install import kiro_env  # late import: install imports config only

        SOW_HOME.mkdir(parents=True, exist_ok=True)
        # Run from ~/.sow-live so no engagement's workspace config (MCP servers, hooks) loads into live agents.
        proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout,
                              cwd=str(SOW_HOME), env=kiro_env())
    except subprocess.TimeoutExpired as e:
        raise KiroError(f"{agent} timed out after {timeout}s") from e
    took = time.time() - t0
    if log_path:
        log_path.write_text(
            f"# agent={agent} model={model} took={took:.1f}s rc={proc.returncode}\n\n## PROMPT\n{prompt}\n\n"
            f"## STDOUT\n{proc.stdout}\n\n## STDERR\n{proc.stderr}\n"
        )
    err = ANSI.sub("", proc.stderr or "")
    if "Error:" in err and not proc.stdout.strip():
        raise KiroError(err.strip().splitlines()[-1][:300])
    result = extract_json(proc.stdout)
    result["_took"] = round(took, 1)
    return result
