---
name: tree-context
description: Use a compact project tree index to reduce unnecessary repository-wide Grep/Glob scans in Claude Code.
disable-model-invocation: true
allowed-tools: Bash, Read, Grep, Glob, Edit, MultiEdit, Write
---

# Tree Context Mode

Task: $ARGUMENTS

Use the compact project tree index before exploring the repository. This Skill helps Claude find likely files and directories faster while avoiding unnecessary repository-wide searches.

## Workflow

1. Run compact context selection for this task:

   ```bash
   python3 .claude/scripts/tree_context.py select --prompt "$ARGUMENTS"
   ```

   If `python3` is unavailable, use:

   ```bash
   python .claude/scripts/tree_context.py select --prompt "$ARGUMENTS"
   ```

2. Read candidate files from the selected context first.
3. If `Grep` is necessary, scope it to candidate directories or clearly relevant directories.
4. Avoid repository-wide `Grep` / `Glob` unless the selected context has no useful candidates.
5. Avoid generated, dependency, build, binary, cache, and log files unless explicitly required.
6. When creating, deleting, or moving files, rely on the `PostToolUse` hook to refresh the tree index.
7. If the index may be stale, rebuild it manually:

   ```bash
   python3 .claude/scripts/tree_context.py build
   ```

## Quality Guardrails

- Treat selected context as a starting point, not complete evidence.
- Before editing, verify the relevant entry point, call site, or configuration path.
- If candidates do not clearly match the task, run a narrow search from likely directories.
- If behavior changes, check nearby tests or include a focused verification step.
- Do not claim the issue is fully handled unless the edited path and verification are clear.

## Candidate Usage Rules

- When candidate files are strong matches, read them first, then follow code relationships as needed.
- When candidate directories are strong matches but files are unclear, search within those directories.
- When candidates are empty or clearly unrelated, return to root modules and use narrow search to relocate.
- For cross-module issues, verify the call chain instead of editing only the first matched file.
- For configuration, routing, permission, authentication, or database issues, check registration or wiring points.

## Response Format

Keep the response compact and prioritize:

- Relevant candidate files
- Minimal plan
- Files changed or to change
- Verification command or result

Do not paste large logs or entire files. Summarize and cite file paths instead.