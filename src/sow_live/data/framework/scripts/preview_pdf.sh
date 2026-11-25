#!/usr/bin/env bash
#
# Render a generated SoW .docx to PDF for visual QA using LibreOffice headless.
#
# Usage:  sow-live preview "<file.docx>" [output_dir]
#
set -euo pipefail

INPUT="${1:?Usage: preview_pdf.sh <file.docx> [output_dir]}"
OUTDIR="${2:-$(dirname "$INPUT")}"

if command -v soffice >/dev/null 2>&1; then
  SOFFICE="soffice"
elif [ -x "/Applications/LibreOffice.app/Contents/MacOS/soffice" ]; then
  SOFFICE="/Applications/LibreOffice.app/Contents/MacOS/soffice"
else
  echo "!! LibreOffice (soffice) not found. Run: sow-live init" >&2
  exit 1
fi

"$SOFFICE" --headless --convert-to pdf --outdir "$OUTDIR" "$INPUT"
echo "Preview PDF written to: $OUTDIR"
