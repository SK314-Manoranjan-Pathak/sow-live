---
name: docx-formatter
description: Use when generating the final Statement of Work .docx file, or when converting assembled SoW content into the branded ShellKode Word document. Runs the python-docx engine that applies exact fonts, colors, cover page, tables, and footer.
---

# DOCX Formatter

Produce the final ShellKode-branded `.docx` by running the generation engine against a content-JSON payload. Never hand-edit `.docx` XML — all styling lives in the script and `@SOW_FRAMEWORK@/templates/style-reference.json`.

## Prerequisite

Installed by `sow-live init` (python-docx is bundled with the package; run the engine through `sow-live docx`).

## How to generate

1. Assemble the complete content payload following `references/content-schema.md`.
2. Write it to a temp file, e.g. `build/content.json`.
3. Run the engine:

```bash
sow-live docx build/content.json "{Client} - {Project Title}.docx"
```

If no output path is given, the script derives one from the cover fields.

## What the engine handles automatically

- A4 page, 25mm margins, footer ("ShellKode Confidential..." + page number)
- Full-page cover artwork with logo + client name + project title + "Prepared By" overlay
- Heading 1/2/3 styles (DM Sans, correct sizes and blues)
- Justified body text (DM Sans 11pt)
- Tables with `#1155CC` white-on-blue headers, thin grey borders, RACI center alignment, phase group rows
- Static Table of Contents built from `h1` blocks
- Embedded architecture diagram image (or a placeholder if missing)

## After generating

- Open/verify the file. Confirm no `{{placeholder}}` tokens remain that should have been filled.
- Check section completeness against `@SOW_FRAMEWORK@/standards/sow-sections.md`.
- Render a PDF for visual QA:

```bash
sow-live preview "<Client - Project Title>.docx"
```

## Customizing branding

Swap `@SOW_FRAMEWORK@/templates/assets/*.png` and edit `@SOW_FRAMEWORK@/templates/style-reference.json`. The script reads all fonts/colors/company facts from that JSON — no code changes needed for a rebrand.
