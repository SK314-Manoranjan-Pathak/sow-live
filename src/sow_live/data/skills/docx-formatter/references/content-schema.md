# Content-JSON schema

The payload passed to `@SOW_FRAMEWORK@/scripts/generate_sow_docx.py` (run it via `sow-live docx`). One top-level object with `cover` and `body`.

```json
{
  "include_toc": true,
  "cover": {
    "client_name": "Acme Manufacturing Private Limited",
    "project_title": "Serverless Data Lake Platform",
    "author": "Manoranjan",
    "website": "www.shellkode.com"
  },
  "body": [ <block>, <block>, ... ]
}
```

## Cover fields

| Field | Purpose |
|-------|---------|
| `client_name` | Blue client legal name on the cover |
| `project_title` | Project title under the client name |
| `author` | Shown in the "Prepared By" corner |
| `website` | Cyan URL in the corner (defaults to www.shellkode.com) |

## Body blocks

Each block is an object with a `block` key. Blocks render in order.

### Headings
```json
{ "block": "h1", "number": "6", "text": "Scope of Work" }
{ "block": "h2", "number": "6.1", "text": "Phase 2A - Core Platform" }
{ "block": "h3", "number": "6.1.1", "text": "AWS Environment Setup" }
```
`number` is optional; omit for unnumbered headings. `h1` blocks populate the Table of Contents.

### Paragraph
```json
{ "block": "p", "text": "Justified body text..." }
```

### Bullets (one level of nesting)
```json
{ "block": "bullets", "items": [
  "Simple bullet",
  { "text": "Parent bullet", "children": ["Sub-bullet A", "Sub-bullet B"] }
]}
```

### Table
```json
{
  "block": "table",
  "header": ["Implementation steps", "ShellKode", "Client"],
  "align_center_cols": [1, 2],
  "rows": [
    { "group": "Phase 2A: Core Platform" },
    ["Provision AWS infrastructure", "R", "I"],
    ["Share API credentials", "C", "R"],
    ["Final sign-off", "I", "A"]
  ]
}
```
- `header` — array of column titles (rendered white-on-blue).
- `align_center_cols` — indices of columns to center (use for R/A/C/I).
- `rows` — each row is an array of cell strings, OR `{ "group": "..." }` for a full-width bold phase separator row.

### Image (architecture diagram)
```json
{ "block": "image", "path": "build/architecture.png", "width_in": 6.5, "caption": "Solution architecture" }
```
If `path` is missing or not found, a labeled placeholder is inserted instead.

### Page break
```json
{ "block": "pagebreak" }
```

## Assembly checklist (canonical order)

1 Service Agreement · 2 About ShellKode · 3 Business Background · 4 Project Overview/Objectives · 5 Architecture Diagram (image) · 6 Scope of Work (phases) · 7 Roles & Responsibilities (table + RACI legend) · 8 Timelines & Deliverables (table) · 9 Effort Estimate (9.1 calculator link, 9.2 commercials table) · 10 Pre-requisites & Assumptions · 11 Out of Scope · 12 Success Criteria · 13 Project Personnel (table) · 14 Duration of Work · 15 Deliverable Acceptance · 16 Terms and Conditions · 17 Acceptance and Signatories (table)
