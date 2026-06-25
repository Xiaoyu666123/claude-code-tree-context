#!/usr/bin/env bash
set -euo pipefail

ROOT="${CLAUDE_PROJECT_DIR:-$(pwd)}"
SCRIPT="$ROOT/.claude/scripts/tree_context.py"
if command -v python3 >/dev/null 2>&1; then
  python3 "$SCRIPT" post-update --root "$ROOT"
elif command -v python >/dev/null 2>&1; then
  python "$SCRIPT" post-update --root "$ROOT"
fi
