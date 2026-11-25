#!/usr/bin/env bash
#
# Export a .drawio architecture diagram to PNG using the draw.io desktop CLI.
# Used for the SoW "Architecture Diagram" section.
#
# Usage:  sow-live diagram <input.drawio> <output.png>
#
set -euo pipefail

INPUT="${1:?Usage: export_diagram.sh <input.drawio> <output.png>}"
OUTPUT="${2:?Usage: export_diagram.sh <input.drawio> <output.png>}"

# Resolve the draw.io CLI per platform
if [ -x "/Applications/draw.io.app/Contents/MacOS/draw.io" ]; then
  CLI="/Applications/draw.io.app/Contents/MacOS/draw.io"
elif command -v drawio >/dev/null 2>&1; then
  CLI="drawio"
else
  echo "!! draw.io CLI not found. Run: sow-live init" >&2
  exit 1
fi

# -x export, -f png, -e embed editable XML, -b 10 border, --scale 2 for crisp output
"$CLI" -x -f png -e -b 10 --scale 2 -o "$OUTPUT" "$INPUT"
echo "Exported: $OUTPUT"
