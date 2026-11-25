# sow-live

Discovery-call assist and branded Statement of Work generator for ShellKode Solutions Architects, built on [Kiro CLI](https://kiro.dev/cli/).

Start it about 5 minutes before a customer discovery call. It transcribes the call locally, fills the SoW brief as people talk, and suggests the questions still needed for a properly scoped SoW (volumes, KPIs, boundaries, residency, integrations, phasing). It answers the customer's technical questions from AWS documentation and their "have you done this before?" questions from the ShellKode wiki. When the call ends, it writes the brief and generates the SoW without going back to you with questions.

macOS only (system-audio capture uses ScreenCaptureKit). Apple Silicon recommended.

## Install

```bash
# uv, if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

uv tool install git+https://github.com/SK314-Manoranjan-Pathak/sow-live
sow-live init
```

`sow-live init` installs whatever is missing and is safe to re-run (it doubles as the repair command):

- Xcode Command Line Tools, Homebrew, `whisper-cpp`, `ffmpeg`, `uv`, `node`, `poppler`, draw.io, LibreOffice and Kiro CLI.
- The SoW skills and the live agents into `~/.kiro/skills` and `~/.kiro/agents`. Every file is tracked in `~/.sow-live/manifest.json`; skills you installed yourself (for example your own `wiki-assistant`) are left alone.
- A marked block in `~/.kiro/settings/permissions.yaml` so the SoW pipeline can read the installed framework without a prompt per file.
- Kiro authentication: your existing `kiro-cli` login, or a Kiro API key stored in the macOS Keychain (never in a file).
- The Whisper `large-v3-turbo` model (about 550 MB) and the system-audio helper, compiled locally.
- Settings in `~/.sow-live/config.toml`: engagements folder (default `~/SoW`), your name as SoW author, call language.

Then, once:

1. Grant **Microphone** and **Screen & System Audio Recording** to your terminal app (System Settings > Privacy & Security) and restart it.
2. `sow-live check`: audio levels, a test transcription, Kiro and wiki access.
3. `sow-live wiki-login`: one-time Google sign-in to the ShellKode wiki.

## Use

```bash
sow-live new "FinServe Capital" "Support assistant"   # one folder per engagement, under ~/SoW
# drop notes, emails, the use-case write-up into ~/SoW/finserve-capital-support-assistant/sol/

sow-live start --client "FinServe" --minutes 60       # ~5 minutes before the call
```

Before the call starts, it reads `sol/` (or asks you to type context), pulls relevant lessons from the ShellKode wiki, and shows the first questions. During the call:

| Command | Effect |
|---|---|
| `a 2` / `x 2` / `d 2` / `p 2` | mark question 2 asked / answered / dismissed / pinned |
| `n <text>` | add a note; treated as a confirmed fact |
| `? <question>` | ask the AWS advisor (AWS docs, regional availability, pricing) |
| `w <question>` | ask the ShellKode wiki |
| `e 2` | expand answer 2 |
| `go` / `r` | start the call clock / refresh now |
| `end` | finish: final pass, brief, admin fields, SoW |
| `quit` | stop without finalizing (`sow-live finalize` later) |

Answers are tagged `[aws]` or `[wiki]`; `⟲Nd` means the answer was verified on an earlier call N days ago and is shown instantly. Wiki answers never name other customers; names and contacts for you only appear as `🔒` lines.

After `end`, files land in the engagement folder:

- `build/brief.md`: the brief, marked as live-captured.
- `build/learnings.md`: the wiki learnings digest used for warnings and assumptions.
- `live/<session>/brief-review.md`: every field with the transcript quote it came from.
- `live/<session>/followup-email.md`: recap and open questions for the customer.

Then it offers to generate the SoW (`sow-live generate`), which runs Kiro CLI in the engagement folder: the `sow-generator` skill sees the live brief, skips the clarifying round and produces the branded `.docx` and a PDF preview.

Other commands:

```bash
sow-live list                    # engagements, calls, SoW status
sow-live open finserve           # open an engagement in Kiro IDE
sow-live generate finserve       # (re)generate the SoW
sow-live learnings finserve      # refresh the wiki learnings digest
sow-live finalize finserve       # re-run the post-call step
sow-live import <old-folder> --client "X"   # bring in an old single-project framework folder
sow-live wiki-seed               # draft the original seed learnings into the wiki (unpublished)
sow-live uninstall               # remove installed files; engagement folders are kept
```

## How it fits together

```
mic ─ffmpeg─┐                                  every ~45 s
            ├─ VAD ─ whisper.cpp (local) ─ transcript ─► sow-live agent (no tools)
system ─────┘                                     fields · questions · flags · lookups
audio                                                 │
                     ┌────────────────────────────────┼──────────────────────────────┐
                     ▼                                ▼                              ▼
         sow-live-advisor                  sow-live-org                    knowledge graph
         awsknowledge + awspricing         shellkode-wiki (read-only)      ~/.sow-live/knowledge.db
         → [aws] answers                   → [wiki] answers, learnings     → follow-ups, reused answers
                     └──────────────────── panel (terminal) ──── end ──► brief → sow-generator → .docx
```

- **Engagement folders** (`~/SoW/<client>-<project>/`) hold `sol/`, `build/`, `live/` and a `.kiro/` with the AWS MCP servers, the knowledge-graph MCP and the IDE hooks. Each client's material stays in its own folder, so the agents can't mix customers.
- **Learnings come from the wiki.** The org agent digests the wiki's Challenges, Solutions and Playbooks pages for the engagement before the call, and fetches more when the call moves to a new topic. If the wiki is unreachable, a small generic fallback is used and the panel says so.
- **Personal knowledge graph.** Every finished call is stored locally: brief fields with evidence, open questions, flags, entities (systems, AWS services, constraints) and verified answers. A follow-up call with the same customer starts from what earlier calls captured; verified answers younger than 30 days are reused instantly. In Kiro, the `sow-knowledge` MCP server (`list_engagements`, `get_engagement`, `search_knowledge`, `find_verified_answers`) lets you query it at any time. Nothing leaves your machine.
- **Privacy.** Audio stays in memory and goes only to the local Whisper server. Transcript text is sent to Kiro's models. Transcripts, briefs and the graph live on your machine only.

## Configuration

Override defaults in `~/.sow-live/config.toml` (defaults: `src/sow_live/data/config.default.json`):

```toml
engagements_root = "~/SoW"
author = "Your Name"
tick_seconds = 45
closing_minutes = 10

[asr]
language = "auto"      # en, or auto for mixed Hindi/English calls

[models]
live = "claude-sonnet-5.5"
final = "claude-opus-5.5"
```

`sow-live paths` shows where everything is.

## Development

```bash
uv tool install --force --reinstall .      # install from a checkout
sow-live start --client "FinServe" --minutes 30 \
  --replay-transcript examples/sample-discovery-call.txt --speed 3 --headless --no-handoff
```

Bump `__version__` in `src/sow_live/__init__.py` with every change to skills, agents or framework files: the first command after an upgrade refreshes the installed copies only when the version changes. Per-tick prompts and raw replies are logged in `<engagement>/live/<session>/ticks/`.

## Rebranding

Replace `src/sow_live/data/framework/templates/assets/*.png`, edit `templates/style-reference.json`, and update the boilerplate in `src/sow_live/data/skills/sow-generator/references/`. See `NOTICE.md` for what belongs to ShellKode.

## License

Code: MIT (`LICENSE`). ShellKode name, logo, artwork and boilerplate: see `NOTICE.md`.
