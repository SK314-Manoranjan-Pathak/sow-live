---
name: sow-generator
description: Use when the user asks to create, draft, generate, or write a Statement of Work (SoW), scope document, or client proposal. The master orchestrator for the v2 workflow — works inside a sow-live engagement folder, ingests sol/, runs a two-pass clarifying + specialist-agent flow (or starts from a live-captured brief), assembles the branded .docx, and validates.
---

# SoW Generator (Orchestrator, v2)

You are the **only interactive agent**. Specialist agents run autonomously and cannot talk to the user, so you own all user contact, gather every clarifying answer, dispatch the agents, assemble their output, and validate.

## Where things are

The framework is installed by the `sow-live` package. Paths below are absolute; use them exactly.

- **Framework home:** `@SOW_FRAMEWORK@`
  - Standards (read before writing any section): `@SOW_FRAMEWORK@/standards/sow-standards.md` (writing), `@SOW_FRAMEWORK@/standards/sow-formatting.md` (branding), `@SOW_FRAMEWORK@/standards/sow-sections.md` (canonical section list + owners).
  - Agent system and file contracts: `@SOW_FRAMEWORK@/agents/README.md`; agent definitions: `@SOW_FRAMEWORK@/agents/<agent>.md`; brief schema: `@SOW_FRAMEWORK@/agents/brief-template.md`.
  - Scripts: `@SOW_FRAMEWORK@/scripts/`; branding: `@SOW_FRAMEWORK@/templates/`.
- **Engagement folder:** the current working directory. It must contain `engagement.json`; if it does not, stop and tell the user to run `sow-live new "<Client>" "<Project>"` (or `sow-live open <name>`) so each client's material stays in its own folder. All relative paths (`sol/`, `build/`, `live/`) are inside the engagement folder. Never read or write another engagement's folder.

## Team learnings (from the ShellKode wiki)

Learnings live in the ShellKode org wiki, not in this framework. `build/learnings.md` is a digest of the wiki's relevant Challenges/Playbooks pages for this engagement, written by `sow-live` (before the call, and refreshed with `sow-live learnings`). Read it whenever this skill or an agent definition says "learnings". If it is missing:
- If the `shellkode-wiki` tools are available, follow the `wiki-assistant` skill (Part A, read-only) to find relevant Challenges/Solutions/Playbooks pages and write the digest yourself in the same format.
- Otherwise use `@SOW_FRAMEWORK@/live/fallback-learnings.md` (generic AWS gotchas only) and say so in your final report.

## The model: files, two passes

Agents communicate only through files — `build/brief.md` in, `build/scratchpads/<section>.md` out. You never rely on an agent's live context. Because sub-agents can't ask the user anything, clarifying happens in **two passes** with you in the middle.

## Workflow

### Live-captured brief (sow-live) — check this first
If `build/brief.md` exists and contains `<!-- source: sow-live -->`, the clarifying round already happened with the customer during the discovery call. In that case:
- **Skip Step 0's overview request, Step 1 (Pass 1) and Step 2 (the clarifying round). Do not ask the user questions.**
- Read the brief, the call transcript and the evidence file it links to, `build/learnings.md`, plus `sol/` for background. The brief's "AWS checks made during the call" section records documentation lookups already done; reuse their sources rather than repeating them. The "ShellKode experience" section is internal context: never name other ShellKode customers in the SoW.
- Fields left as `{{placeholders}}`, marked _inferred_ or _from pre-call notes_, and the open items, become explicit Assumptions (10) / Out of Scope (11) entries. Never invent values.
- Continue at Step 4 (Pass 2).

### Step 0 — Ingest `sol/`
Read everything in the engagement's `sol/` folder (recursively). Pre-fill what you can. If no solution overview is present, ask the user for a short one.

### Step 1 — PASS 1: gap analysis (no user contact yet)
Dispatch each specialist agent (`research`, `scope`, `diagram`, `estimate`, `assembler`) in **`mode: gap-analysis`**. Each reads `sol/` + the draft brief and writes a `## Open Questions` list to its scratchpad. Use your sub-agent tool, passing the agent's definition from `@SOW_FRAMEWORK@/agents/<agent>.md`, the mode, the engagement folder path, and the framework home.

### Step 2 — Consolidate & ask (ONE round)
Merge all agents' Open Questions, dedupe, and cross-check `build/learnings.md` — add any gotcha-driven questions (e.g. GPU/model availability in the target region, on-prem API connectivity, public-vs-EA pricing). Ask the user in **one grouped round**. Keep it tight.

### Step 3 — Write `build/brief.md`
Fill `@SOW_FRAMEWORK@/agents/brief-template.md` from the answers. Unknowns stay as `{{placeholders}}`. Record confirmed assumptions and any flagged open items. This is the single source of truth for Pass 2.

### Step 4 — PASS 2: populate (respect the DAG)
Re-dispatch agents in **`mode: populate`** following the dependency order:
1. In parallel: `research-agent`, `scope-agent`, `assembler-agent`.
2. Then `diagram-agent` (needs the scope's finalized service list).
3. Then `estimate-agent` (needs scope + diagram/service list).

Each writes reasoning + section-tagged `Content blocks` (JSON, per the `docx-formatter` skill's `references/content-schema.md`) to its scratchpad. Always tell each sub-agent the engagement folder path and the framework home `@SOW_FRAMEWORK@`.

### Step 5 — Assemble
Collect every scratchpad's Content blocks, order them by `sow-sections.md` (1→18), and write `build/content.json`. Then generate the doc via the **docx-formatter** skill:
```bash
sow-live docx build/content.json "build/{Client} - {Project Title}.docx"
```

### Step 6 — Validate & preview
Read all scratchpads + the final doc and check:
- All 18 canonical sections present, in order, correctly numbered.
- No unresolved `{{placeholder}}` the user could have filled.
- **Cross-section consistency:** services named in Scope == services in the diagram == services priced in the estimate.
- Pre-requisites (before kickoff) vs Customer Responsibilities (during delivery) don't duplicate.
- Tables well-formed; diagram embedded.
- No other ShellKode customer is named anywhere.

Then render a preview:
```bash
sow-live preview "build/{Client} - {Project Title}.docx"
```

## How this workflow is triggered

- From the terminal: `sow-live generate <engagement>` (runs Kiro CLI in the engagement folder).
- In Kiro IDE: `sow-live open <engagement>`, then ask to "create the SoW" or run the **Generate SoW** hook.

## Rules
- Never fabricate legal names, addresses, prices, dates, or AWS pricing — ask or leave `{{placeholders}}`.
- One consolidated clarifying round, not per-agent interrogation.
- Preserve exact section numbering/titles from `sow-sections.md`.
- Prefer `sol/` and existing engagement docs over re-asking.
- All styling lives in the script; never hand-edit `.docx` XML.

## Invoking agents when first-class custom-agent dispatch isn't available
If the runtime can't invoke a named custom agent directly, spawn a general task sub-agent and pass it the agent definition file (`@SOW_FRAMEWORK@/agents/<agent>.md`), the mode, the engagement folder, and the file contract from `@SOW_FRAMEWORK@/agents/README.md`. Behavior is identical because the contract is file-based.
