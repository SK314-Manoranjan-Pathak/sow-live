"""Paths and configuration.

Layout on the user's machine:
  ~/.sow-live/                 SOW_HOME (override with SOW_LIVE_HOME)
    config.toml                personal settings (overrides data/config.default.json)
    framework/                 installed framework: agents, standards, scripts, templates, prompts
    bin/syscap                 system-audio helper, compiled by `sow-live init`
    models/                    Whisper model
    knowledge.db               personal knowledge graph
    manifest.json              files sow-live installed under ~/.kiro (for upgrade/uninstall)
  ~/.kiro/skills, ~/.kiro/agents   global Kiro skills/agents (override with SOW_KIRO_HOME)
  ~/SoW/<engagement>/          one folder per engagement (engagements_root in config.toml)
"""

from __future__ import annotations

import copy
import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path

PKG_DIR = Path(__file__).resolve().parent
DATA = PKG_DIR / "data"
DEFAULT_CONFIG = DATA / "config.default.json"

SOW_HOME = Path(os.environ.get("SOW_LIVE_HOME", "~/.sow-live")).expanduser()
KIRO_HOME = Path(os.environ.get("SOW_KIRO_HOME", "~/.kiro")).expanduser()

FRAMEWORK = SOW_HOME / "framework"
BIN_DIR = SOW_HOME / "bin"
MODELS_DIR = SOW_HOME / "models"
USER_CONFIG = SOW_HOME / "config.toml"
MANIFEST = SOW_HOME / "manifest.json"
KNOWLEDGE_DB = SOW_HOME / "knowledge.db"
SYSCAP_BIN = BIN_DIR / "syscap"

KIRO_SKILLS = KIRO_HOME / "skills"
KIRO_AGENTS = KIRO_HOME / "agents"


def framework_file(*parts: str) -> Path:
    """A framework file, preferring the installed copy and falling back to the package data."""
    installed = FRAMEWORK.joinpath(*parts)
    return installed if installed.exists() else DATA.joinpath("framework", *parts)


CATALOG = framework_file("live", "field-catalog.json")


def _deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def _toml_value(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def dump_toml(d: dict) -> str:
    lines, tables = [], []
    for k, v in d.items():
        (tables if isinstance(v, dict) else lines).append((k, v))
    out = [f"{k} = {_toml_value(v)}" for k, v in lines]
    for name, table in tables:
        out += ["", f"[{name}]"] + [f"{k} = {_toml_value(v)}" for k, v in table.items() if not isinstance(v, dict)]
    return "\n".join(out) + "\n"


def read_user_config() -> dict:
    if USER_CONFIG.exists():
        return tomllib.loads(USER_CONFIG.read_text())
    return {}


def write_user_config(updates: dict) -> None:
    SOW_HOME.mkdir(parents=True, exist_ok=True)
    USER_CONFIG.write_text(dump_toml(_deep_merge(read_user_config(), updates)))


@dataclass
class Config:
    raw: dict

    @classmethod
    def load(cls) -> "Config":
        base = json.loads(DEFAULT_CONFIG.read_text())
        return cls(_deep_merge(base, read_user_config()))

    def __getitem__(self, key):
        return self.raw[key]

    def get(self, key, default=None):
        return self.raw.get(key, default)

    @property
    def asr_model(self) -> Path:
        return MODELS_DIR / self.raw["asr"]["model_file"]

    @property
    def engagements_root(self) -> Path:
        return Path(self.raw["engagements_root"]).expanduser()


def load_catalog() -> list[dict]:
    """Flat list of fields, each with its brief section title attached."""
    data = json.loads(CATALOG.read_text())
    out = []
    for section in data["sections"]:
        for f in section["fields"]:
            out.append({**f, "section": section["title"]})
    return out
