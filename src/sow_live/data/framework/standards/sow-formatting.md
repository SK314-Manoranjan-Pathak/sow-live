# SoW Formatting Spec (ShellKode brand)

This is the exact visual specification for ShellKode SoW `.docx` output, extracted from the reference proposal. The `docx-formatter` skill and `@SOW_FRAMEWORK@/scripts/generate_sow_docx.py` (run it via `sow-live docx`) are the source of truth; this file keeps the values visible to the agent. If you edit styling, update `@SOW_FRAMEWORK@/templates/style-reference.json` and the script together.

## Page

- A4 (210 × 297 mm), portrait
- Margins: 25 mm all sides
- Footer on body pages: "ShellKode Confidential - for limited purposes only" + page number

## Fonts

| Use | Font | Notes |
|-----|------|-------|
| Body text | **DM Sans** 11pt | Justified |
| Headings | **DM Sans** | see sizes below |
| Table of Contents title | **Albert Sans** 20pt bold | color `#1A4BD2` |
| Cover "Prepared By" label | **Plus Jakarta Sans** 13pt | white |
| Table headers (some) | **Space Grotesk** bold | white on blue |
| Fallback | Arial 11pt | doc default only |

## Colors

| Token | Hex |
|-------|-----|
| Primary / Heading 1 & 2 blue | `#1A4BD2` |
| Heading 3 / sub-heading blue | `#1155CC` |
| Cover client-name blue | `#0D66C6` |
| Table header fill | `#1155CC` |
| Table header text | `#FFFFFF` |
| Cover URL cyan | `#00B0F0` |
| Cover light text | `#FFFFFF` |
| Body text | `#000000` |

## Heading sizes

| Level | Font | Size | Bold | Color |
|-------|------|------|------|-------|
| Heading 1 (numbered section) | DM Sans | 18pt | yes | `#1A4BD2` |
| Heading 2 (sub-section) | DM Sans | 14pt | yes | `#1A4BD2` |
| Heading 3 (capability) | DM Sans | 14pt | yes | `#1155CC` |

## Cover page

The cover is a **full-page background image** (`@SOW_FRAMEWORK@/templates/assets/cover-art.png`, A4 aspect — blue diagonal bands, dark bottom-left corner, building artwork) with these overlays:

1. **ShellKode logo** (`@SOW_FRAMEWORK@/templates/assets/shellkode-logo.png`) — top-left
2. **Client legal name** — DM Sans 19pt bold, `#0D66C6`
3. **Project title** — DM Sans 17pt, black
4. **"Prepared By:"** block in the dark bottom-left corner:
   - Label: Plus Jakarta Sans 13pt white
   - Author name: DM Sans 11pt white
   - `www.shellkode.com`: DM Sans 11pt cyan `#00B0F0`

## Tables

- Header row: fill `#1155CC`, text white `#FFFFFF`, bold
- Header font: DM Sans (or Space Grotesk) bold
- Body: DM Sans 10pt, black
- Thin grey borders (`#BFBFBF`, 0.5pt)
- RACI tables: center-align the R/A/C/I columns; left-align the step description
- Phase group rows span the full width and are bold

## Output conventions

- Generate the `.docx` by calling `@SOW_FRAMEWORK@/scripts/generate_sow_docx.py` (run it via `sow-live docx`) with a JSON content payload
- Filename: `{Client} - {Project Title}.docx`
- Never hand-build XML; always go through python-docx via the script so styles stay consistent
