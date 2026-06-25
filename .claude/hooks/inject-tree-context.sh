#!/usr/bin/env bash
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SCRIPT="$ROOT/.claude/scripts/tree_context.py"
INPUT="$(cat)"

if command -v python3 >/dev/null 2>&1; then
  printf '%s' "$INPUT" | python3 "$SCRIPT" inject --root "$ROOT"
elif command -v python >/dev/null 2>&1; then
  printf '%s' "$INPUT" | python "$SCRIPT" inject --root "$ROOT"
else
  # Do not block the user's prompt if Python is unavailable.
  echo "<tree-context compact=\"true\">Python not found; tree context hook skipped.</tree-context>"
fi
