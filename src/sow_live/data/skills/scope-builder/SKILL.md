---
name: scope-builder
description: Use when structuring the Scope of Work, phases, deliverables, or Roles and Responsibilities (RACI) sections of a Statement of Work. Turns a project brief into phased, task-level scope aligned with AWS best practices.
---

# Scope Builder

Turn a high-level project brief into a structured, phased Scope of Work plus the matching Roles & Responsibilities (RACI) and Timelines & Deliverables tables.

## Output shape

Produce content-JSON blocks (see the `docx-formatter` skill's `references/content-schema.md`) for three sections:
1. **Scope of Work** — `h1`, then per phase: `h2` (phase), `p` (objective), then per capability `h3` + `bullets`.
2. **Roles and Responsibilities** — a `table` with group rows per phase and R/A/C/I cells.
3. **Timelines and Deliverables** — a `table` of phase / week / milestone / deliverable.

## How to build phases

1. Group capabilities into 2–4 phases. Common pattern: Core Platform → Enhancements → Advanced/Optional.
2. Each phase starts with a one-sentence objective ("The objective of this phase is to...").
3. Each capability is an `h3` sub-section with a bulleted task list. Tasks must be concrete and verifiable.
4. Validate AWS service choices with the `awsknowledge` MCP (cloud-architect Power) — confirm the service exists, is available in the target region, and follows Well-Architected guidance.
5. Use nested bullets (one level) for sub-tasks.

See `references/phase-patterns.md` for reusable phase archetypes.

## RACI rules

- One row per implementation step; a spanning `{"group": "Phase X: ..."}` row precedes each phase's steps.
- Columns: `["Implementation steps", "ShellKode", "{{client_short_name}}"]`.
- Set `align_center_cols: [1, 2]` so the R/A/C/I marks center.
- Delivery/build steps: ShellKode = R, client = I or C.
- Client-provided inputs (credentials, APIs, access): ShellKode = C, client = R.
- Sign-off rows: ShellKode = I, client = A.
- Testing & UAT: ShellKode = C, client = R.

## Timelines rules

- Columns: `["Phase", "Timelines", "Milestones/Key Activities", "Deliverables"]`.
- Use week ranges (Week 1, Week 2–3, etc.).
- Note where phases run in parallel.
- Every row must have a concrete deliverable (e.g. "UAT sign-off", "Chat interface connected to backend").
