# SoW Writing Standards

These standards govern how every ShellKode Statement of Work is written. They apply whenever a SoW or any SoW section is being drafted.

## Voice and tone

- Professional, confident, and precise. This is a client-facing commercial proposal.
- Third person. Refer to the delivery org as **ShellKode** and the customer as the **Client** (or the defined short name, e.g. "Cx").
- Present/future tense for scope ("ShellKode will provision...", "The platform enables...").
- No marketing hyperbole, no exclamation points, no em dashes as sentence breaks.
- Every scope item must be concrete and verifiable. Avoid vague verbs like "handle" or "support" without saying what and how.

## Canonical section order

The authoritative section list, numbering, titles, and owning agents live in **`sow-sections.md`** (always-on steering). Use it as the single source of truth for structure. The cover page precedes the Table of Contents, which precedes section 1.

## Section-specific rules

- **Scope of Work**: organize into phases (e.g. Phase 2A, 2B...). Each phase gets an objective sentence, then numbered sub-capabilities. Each capability is a bulleted list of concrete tasks.
- **Roles and Responsibilities**: use the RACI convention — R (Responsible), A (Accountable), C (Consulted), I (Informed). One row per implementation step, phase headers as spanning rows.
- **Pre-requisites**: everything the client must provide before/during the engagement (access, credentials, APIs, nominated users, sign-off SLAs).
- **Assumptions**: constraints the estimate depends on (region, user count, auth mechanism, pricing basis, no fine-tuning, etc.).
- **Out of Scope**: mirror the assumptions — anything explicitly not included.
- **Success Criteria**: each bullet must be observable/testable during UAT.

## RACI legend (always include below the roles table)

- **R** – Responsible (does the work)
- **A** – Accountable (owns the outcome / final sign-off)
- **C** – Consulted (provides input)
- **I** – Informed (kept up to date)

## Placeholders

Use `{{double_curly}}` tokens for values the user hasn't supplied yet (e.g. `{{effective_date}}`, `{{client_legal_name}}`). Never invent legal entity names, addresses, or prices — ask the user or leave a clearly-marked placeholder.

## Numbers and estimates

- Never fabricate pricing. Pull real figures from the pricing MCP or ask the user.
- Cost variance language: architecture/cost estimates are "within acceptable variance of manual calculation (based on public API pricing)".
- Effort estimates are expressed in weeks per role in the Commercials table.
