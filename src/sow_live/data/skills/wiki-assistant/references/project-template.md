# Reference: project & customer page shape

Load this only when drafting or updating a Project or Customer page. It mirrors the
org-standard templates. Emit front matter as a fenced ```yaml block (Outline renders `---`
front matter as a heading, so never use `---` delimiters).

## Project page (ask the user: which team — AI / Cloud / Data — and the customer)

Target collection: `Projects · <team>`. Required: customer, project, stage, at least one
solution tag, a Use case, and at least one challenge. Everything else is optional but
helps the next team.

````
```yaml
customer: "Acme EduTech"        # required
project: "AI Voice Tutor"       # required
status: active                  # active | on-hold | closed
stage: poc                      # discovery | poc | implementation | production | support
in_production: false
start_date: "2025-03"           # YYYY-MM
delivered_date: ""              # YYYY-MM, blank if not delivered
owner: "Priya S."
team: ["Priya S.", "Rahul M."]
industry: "education"
solution_tags: [voice, multi-agent]      # controlled vocabulary (see vocabulary.md)
partner_tags: [aws, elevenlabs]
aws_services: [bedrock, transcribe, lambda]
volumetrics: "~5k calls/day, 12k MAU"
sow_url: ""                     # link raw artifacts, never paste them in
arch_diagram_url: ""
live_demo_url: ""
demo_doc_url: ""
```
````

Body sections (in order):

- `## Use case` — one paragraph: what problem, for whom.
- `## Solution summary` — how we solved it, high level.
- `## Functional flow` — step by step, or link the architecture diagram + short narrative.
- **Team-specific section** — AI adds `## Models & evaluation` (plus `models` and
  `frameworks` front-matter fields); Cloud adds `## Architecture & migration` (plus
  `source_environment`, `migration_strategy`, `iac`); Data adds `## Data architecture`
  (plus `data_sources`, `data_volume`, `platform`). Fetch the team's template with
  `list_templates` / `fetch` to get its exact extra fields.
- `## Challenges & workarounds` — the most valuable section. One block per challenge:
  - **Challenge:** what broke or was hard
  - **Workaround:** what we did
  - **Reusable insight:** the takeaway for future projects
  If the source doesn't give the workaround or insight, write `_gap — to confirm_` rather
  than inventing it.
- `## Outcome` — did it work, caveats, current state.
- `## Notes` — anything else.

Link raw files (SoW, diagrams, demos) via the `*_url` fields; never paste their contents
into the wiki.

## Customer page

Target collection: `Customers`. One page per customer; `customer` must match the project
pages exactly.

````
```yaml
customer: "Acme EduTech"        # required, exact match to project pages
industry: "education"
region: "India"
relationship: active            # prospect | active | past
first_engagement: "2025-03"
account_owner: "Priya S."
teams: [AI]                     # teams that have worked with them
```
````

- `## Overview` — who they are and what they care about.
- `## Engagements` — link each project page, newest first, one line each.
- `## Working with them` — decision process, constraints, compliance, preferred tools.
- `## Notes` — anything else.
