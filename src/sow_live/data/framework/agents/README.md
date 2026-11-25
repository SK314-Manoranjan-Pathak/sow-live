# SoW Specialist Agents (v2)

Five specialist agents populate the SoW, coordinated by the main **orchestrator** (the `sow-generator` skill). Agents are grouped by capability and dependency — not one per section.

## The golden rule: agents communicate through files only

Agents never depend on each other's live context. They read and write files, all inside the **engagement folder** the orchestrator gives you (never another engagement's folder). The framework home is `@SOW_FRAMEWORK@`; standards are in `@SOW_FRAMEWORK@/standards/`.

- **Input:** `build/brief.md` (confirmed inputs + assumptions, written by the orchestrator) and the raw material in `sol/`.
- **Output:** `build/scratchpads/<section-key>.md` — reasoning **and** the emitted content block(s).

This makes the invocation mechanism swappable (first-class Kiro custom agent or a task sub-agent) and makes every run auditable and resumable.

## Because sub-agents can't talk to the user: the two-pass flow

Any agent invoked as a sub-agent runs autonomously and **cannot ask the user anything**. Only the orchestrator is interactive. So:

1. **Pass 1 — Gap analysis:** the orchestrator runs each agent in `mode: gap-analysis`. The agent reads `sol/` + the draft brief and writes a `## Open Questions` list to its scratchpad. No user contact.
2. **Consolidate + ask:** the orchestrator merges all agents' questions, dedupes, cross-checks `build/learnings.md` (wiki learnings digest), and asks the user in one grouped round. Answers + assumptions are written to `build/brief.md`.
3. **Pass 2 — Populate:** the orchestrator re-runs each agent in `mode: populate`. The agent reasons in its scratchpad and emits its section content block(s).

## The agents

| Agent | Sections (per `sow-sections.md`) | Reuses |
|-------|----------------------------------|--------|
| `research-agent` | 1 Service Agreement, 2 About ShellKode, 3 Business Background | `fetch` MCP, `sol/`, sow-generator boilerplate refs |
| `scope-agent` | 5 Scope of Work, 6 Roles & Responsibilities, 7 Timelines & Deliverables | scope-builder skill, `awsknowledge` MCP |
| `diagram-agent` | 4 Architecture Diagram | aws-architecture-diagram skill, `export_diagram.sh` |
| `estimate-agent` | 8 Effort Estimate | estimate-builder skill, `awspricing` + `aws-calculator` MCPs |
| `assembler-agent` | 9–18 (Pre-reqs, Assumptions, Out of Scope, Success Criteria, Customer Responsibilities, Project Personnel, Duration, Deliverable Acceptance, Terms, Signatories) | boilerplate refs, `brief.md` |

## Dependency DAG (Pass 2 ordering)

```
brief.md
  ├── research-agent      (independent)
  ├── assembler-agent     (independent)
  └── scope-agent         (independent)
        └── diagram-agent       (needs scope)
              └── estimate-agent (needs scope + diagram/services)
```

research-agent, assembler-agent, and scope-agent can run in parallel. diagram-agent runs after scope. estimate-agent runs after diagram (needs the finalized service list).

## Scratchpad format (every agent writes this)

```markdown
# Scratchpad: <section name(s)>  —  agent: <agent>  mode: <gap-analysis|populate>

## Sources consulted
- <files from sol/ and brief.md sections used>

## Open Questions        (Pass 1 primary output)
- Q: ...  (why it matters / what it blocks)

## Reasoning             (Pass 2)
- <decisions, tradeoffs, assumptions applied, learnings hits>

## Content blocks        (Pass 2 — the actual SoW JSON blocks)
```json
[ { "block": "h1", "number": "5", "text": "Scope of Work" }, ... ]
```

## Assumptions & flags
- <assumptions made, gaps left as {{placeholders}}, learnings raised>
```

The orchestrator merges every agent's **Content blocks** (in section order) into `build/content.json`, then runs the docx engine.

## Section keys (scratchpad filenames)

`service-agreement`, `about-shellkode`, `business-background`, `architecture-diagram`, `scope-of-work`, `roles-responsibilities`, `timelines-deliverables`, `effort-estimate`, `prerequisites`, `assumptions`, `out-of-scope`, `success-criteria`, `customer-responsibilities`, `project-personnel`, `duration-of-work`, `deliverable-acceptance`, `terms-conditions`, `signatories`.

(An agent that owns several sections may write one scratchpad per section, or one combined scratchpad with clearly separated blocks — either is fine as long as the content blocks are section-tagged.)
