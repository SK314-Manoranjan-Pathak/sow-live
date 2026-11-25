# Canonical SoW Section List (v2)

The authoritative section order and numbering for every ShellKode SoW. Matches the standard proposal structure. The Table of Contents is built from these; the cover page precedes it.

| # | Section | Owner agent | Notes |
|---|---------|-------------|-------|
| 1 | Service Agreement | research-agent | Legal preamble: both parties, offices, effective/expiration dates, "complete agreement" clause |
| 2 | About ShellKode | research-agent | Standard company boilerplate |
| 3 | Business Background | research-agent | Client business/industry context **and** the problem/objective driving the engagement (folds in the old "Project Overview / Objectives") |
| 4 | Architecture Diagram | diagram-agent | Embedded AWS architecture image (`.drawio` → PNG) |
| 5 | Scope of Work | scope-agent | Phased scope; per phase an objective + capabilities as bulleted tasks |
| 6 | Roles and Responsibilities | scope-agent | RACI table (R/A/C/I) per step, grouped by phase, + RACI legend |
| 7 | Timelines and Deliverables | scope-agent | Phase / week / milestone / deliverable table |
| 8 | Effort Estimate | estimate-agent | AWS Pricing Calculator link + itemized infra costs + Commercials table |
| 9 | Pre-requisites | assembler-agent | Access, credentials, tools, approvals needed **before** work begins |
| 10 | Assumptions | assembler-agent | Underlying conditions, constraints, dependencies the proposal rests on |
| 11 | Out of Scope | assembler-agent | Explicit exclusions |
| 12 | Success Criteria | assembler-agent | Measurable, UAT-verifiable acceptance benchmarks |
| 13 | Customer Responsibilities | assembler-agent | Ongoing inputs/access/support the client must provide during delivery |
| 14 | Project Personnel | assembler-agent | Key delivery roles and their responsibilities (table) |
| 15 | Duration of Work | assembler-agent | When work starts, schedule governance, change-order handling |
| 16 | Deliverable Acceptance | assembler-agent | 10-day review/accept/reject process |
| 17 | Terms and Conditions | assembler-agent | Change management, jurisdiction, travel, working hours, indemnification, termination |
| 18 | Acceptance and Signatories of the Proposal | assembler-agent | Two-column signature block |

## Distinctions to respect (v2 change)

- **Pre-requisites (9)** = what's needed *before kickoff*. **Customer Responsibilities (13)** = what the client must keep providing *during delivery*. Keep them separate; don't duplicate items across both.
- **Assumptions (10)** are the estimate/feasibility conditions; **Out of Scope (11)** mirrors them as explicit exclusions.
- **Business Background (3)** now also carries the problem statement + objectives (previously a separate "Project Overview" section).

## Placeholders

Use `{{double_curly}}` tokens for any value the user hasn't supplied (dates, addresses, rates, calculator link). Never invent legal names, addresses, prices, or dates.
