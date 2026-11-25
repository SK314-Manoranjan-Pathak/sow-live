---
name: estimate-builder
description: Use when building the Effort Estimate, Commercials, or AWS cost sections of a Statement of Work. Pulls real AWS pricing, generates a shareable AWS Pricing Calculator link, and builds the effort and commercials tables.
---

# Estimate Builder

Produce the **Effort Estimate** section: an AWS infrastructure cost estimate (with a shareable Pricing Calculator link) plus the resource Commercials table.

## Two distinct pricing tools — use the right one

| Need | MCP server | What it returns |
|------|-----------|-----------------|
| Per-unit AWS pricing for cost tables | `awspricing` (cloud-architect Power) | Raw Price List data + cost report |
| Shareable calculator link for the client | `aws-calculator` (separate install) | Real `https://calculator.aws/#/estimate?id=...` URL |

If the `aws-calculator` MCP is not installed, insert a placeholder note and still provide the itemized cost table from `awspricing`.

## Workflow

### Step 1 — Identify billable AWS services
From the architecture and scope, list the AWS services and their configurations (instance types, storage, region, request volumes). Use the target region from the assumptions (e.g. `ap-south-1`).

### Step 2 — Get unit pricing (`awspricing`)
Follow the mandatory discovery workflow: `get_pricing_service_codes` → `get_pricing_service_attributes` → `get_pricing_attribute_values` → `get_pricing`. Then optionally `generate_cost_report` for a breakdown.

### Step 3 — Build the shareable calculator link (`aws-calculator`)
Pass the same service list to the calculator MCP to create an estimate and capture the returned `calculator.aws` URL. Put this URL in the "AWS Pricing Calculator" sub-section (9.1).

### Step 4 — Effort / Commercials table
Build the Commercials table from the team plan. Columns: `["Resource", "Duration (Weeks)", "Total Cost INR"]`. One row per role.
See `references/rate-cards.md` for role definitions and estimation guidance. **Never invent rates** — ask the user for the rate card or leave `{{cost}}` placeholders.

## Section output (content-JSON)

Effort Estimate is **section 8** in the canonical list (`sow-sections.md`).

```
{ "block": "h1", "number": "8", "text": "Effort Estimate" }
{ "block": "h2", "number": "8.1", "text": "AWS Pricing calculator:" }
{ "block": "p", "text": "Estimated monthly AWS cost: {{amount}}. Shareable estimate: <calculator.aws url>" }
{ "block": "h2", "number": "8.2", "text": "Commercials" }
{ "block": "table", "align_center_cols": [1,2], "header": ["Resource","Duration (Weeks)","Total Cost INR"], "rows": [...] }
```

## Rules
- All AWS pricing must come from a pricing MCP or the user. No guessing.
- State the pricing basis (on-demand vs RI/SP) and region in an assumption line.
- Cost estimates are "within acceptable variance based on public API pricing".
