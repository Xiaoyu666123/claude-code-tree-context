#!/usr/bin/env python3
"""
Tree Context for Claude Code

Builds and injects a compact repository tree context so Claude Code can avoid
broad, repeated Grep/Glob scans.

No third-party dependencies.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence

DEFAULT_IGNORE_DIRS = {
    ".git", ".hg", ".svn", ".idea", ".vscode",
    "node_modules", "dist", "build", "target", "out", ".next", ".nuxt",
    ".turbo", ".cache", "coverage", "logs", "log", "vendor",
    ".venv", "venv", "env", "__pycache__", ".pytest_cache", ".mypy_cache",
    ".gradle", ".m2", "bin", "obj",
}

DEFAULT_IGNORE_GLOBS = [
    ".claude/context/**",
    "**/*.min.js",
    "**/*.map",
    "**/*.log",
    "**/*.tmp",
    "**/*.cache",
    "**/*.png",
    "**/*.jpg",
    "**/*.jpeg",
    "**/*.gif",
    "**/*.webp",
    "**/*.ico",
    "**/*.pdf",
    "**/*.zip",
    "**/*.tar",
    "**/*.gz",
    "**/*.7z",
    "**/*.rar",
    "**/*.exe",
    "**/*.dll",
    "**/*.so",
    "**/*.dylib",
    "**/*.class",
    "**/*.jar",
    "**/*.war",
]

IMPORTANT_FILES = {
    "package.json", "pnpm-workspace.yaml", "turbo.json", "vite.config.ts", "vite.config.js",
    "tsconfig.json", "next.config.js", "next.config.ts",
    "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml", "yarn.lock", "bun.lock", "bun.lockb",
    "pyproject.toml", "requirements.txt", "poetry.lock", "Pipfile", "Pipfile.lock", "setup.py",
    "go.mod", "go.sum", "Cargo.toml", "Cargo.lock", "pom.xml", "build.gradle", "settings.gradle",
    "Gemfile.lock", "composer.lock", "gradle.lockfile",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    "README.md", "CLAUDE.md",
}
# Chinese task terms -> likely path/code keywords. Extend this map for your own projects.
SYNONYMS = {
    "登录": ["login", "signin", "sign-in", "auth", "session", "token", "user"],
    "认证": ["auth", "authentication", "authorize", "permission", "token"],
    "权限": ["auth", "permission", "role", "acl", "rbac", "policy"],
    "用户": ["user", "account", "member", "profile"],
    "导出": ["export", "download", "excel", "xlsx", "csv"],
    "导入": ["import", "upload", "excel", "xlsx", "csv"],
    "报表": ["report", "dashboard", "stat", "statistics"],
    "接口": ["api", "controller", "route", "router", "endpoint", "service"],
    "路由": ["route", "router", "routes", "controller"],
    "数据库": ["db", "database", "sql", "mapper", "model", "entity", "repository", "dao"],
    "配置": ["config", "settings", "application", "yaml", "yml", "properties"],
    "测试": ["test", "spec", "pytest", "unittest", "jest"],
    "前端": ["frontend", "web", "src", "page", "component", "view"],
    "后端": ["backend", "server", "controller", "service", "api"],
    "日志": ["log", "logger", "logging"],
    "错误": ["error", "exception", "fail", "failure", "bug"],
    "任务": ["task", "job", "scheduler", "cron", "worker"],
    "文件": ["file", "upload", "download", "storage"],
    "图片": ["image", "picture", "avatar", "upload"],
    "密码": ["password", "passwd", "pwd", "credential", "secret"],
    "加密": ["crypto", "encrypt", "decrypt", "hash", "cipher"],
    "安全": ["security", "auth", "permission", "audit", "risk"],
}
CODE_EXTS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".vue", ".java", ".go", ".rs", ".c", ".h",
    ".cpp", ".hpp", ".cs", ".php", ".rb", ".kt", ".swift", ".scala", ".sh", ".ps1",
    ".sql", ".html", ".css", ".scss", ".less", ".xml", ".json", ".yaml", ".yml",
    ".toml", ".properties", ".md",
}

INDEX_SCHEMA = 2
RENDER_VERSION = "ascii-tree-v1"


def eprint(*args: object) -> None:
    print(*args, file=sys.stderr)


def project_root(value: str | None = None) -> Path:
    root = value or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return Path(root).resolve()


def context_dir(root: Path) -> Path:
    return root / ".claude" / "context"


def write_text_atomic(path: Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)

def load_custom_ignore(root: Path) -> tuple[set[str], list[str]]:
    dirs = set(DEFAULT_IGNORE_DIRS)
    globs = list(DEFAULT_IGNORE_GLOBS)
    ignore_file = root / ".claude" / "tree-context.ignore"
    if ignore_file.exists():
        for raw in ignore_file.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.endswith("/"):
                dirs.add(line.rstrip("/"))
            else:
                globs.append(line)
    return dirs, globs


def posix_rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def is_ignored(rel: str, ignore_dirs: set[str], ignore_globs: Sequence[str]) -> bool:
    p = PurePosixPath(rel)
    if any(part in ignore_dirs for part in p.parts):
        return True
    return any(fnmatch.fnmatch(rel, pattern) for pattern in ignore_globs)


def run_git_files(root: Path) -> list[str] | None:
    try:
        subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--is-inside-work-tree"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
        proc = subprocess.run(
            ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    except Exception:
        return None


def walk_files(root: Path, ignore_dirs: set[str], ignore_globs: Sequence[str]) -> list[str]:
    result: list[str] = []
    for current, dirnames, filenames in os.walk(root):
        cur = Path(current)
        # prune ignored directories in-place
        kept_dirs = []
        for d in dirnames:
            rel = posix_rel(cur / d, root)
            if is_ignored(rel, ignore_dirs, ignore_globs):
                continue
            kept_dirs.append(d)
        dirnames[:] = kept_dirs
        for filename in filenames:
            path = cur / filename
            rel = posix_rel(path, root)
            if not is_ignored(rel, ignore_dirs, ignore_globs):
                result.append(rel)
    return result


def collect_files(root: Path) -> list[str]:
    ignore_dirs, ignore_globs = load_custom_ignore(root)
    files = run_git_files(root)
    if files is None:
        files = walk_files(root, ignore_dirs, ignore_globs)
    filtered = [f for f in files if not is_ignored(f, ignore_dirs, ignore_globs)]
    return sorted(set(filtered))


def sha256_lines(lines: Sequence[str]) -> str:
    h = hashlib.sha256()
    for line in lines:
        h.update(line.encode("utf-8", errors="ignore"))
        h.update(b"\n")
    return h.hexdigest()

def index_config_hash(ignore_dirs: set[str], ignore_globs: Sequence[str]) -> str:
    payload = {
        "ignore_dirs": sorted(ignore_dirs),
        "ignore_globs": list(ignore_globs),
        "important_files": sorted(IMPORTANT_FILES),
        "render_version": RENDER_VERSION,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).splitlines()
    return sha256_lines(encoded)

def build_tree_lines(files: Sequence[str], max_depth: int = 4, max_lines: int = 500) -> list[str]:
    tree: dict = {}
    for rel in files:
        parts = rel.split("/")
        if not parts:
            continue
        # Keep important root files even if depth limit is low.
        if len(parts) == 1:
            tree.setdefault(parts[0], None)
            continue
        limited = parts[:max_depth]
        node = tree
        for i, part in enumerate(limited):
            is_last = i == len(limited) - 1
            if is_last:
                if len(parts) > max_depth:
                    node.setdefault(part, {})
                    node[part].setdefault("...", None)
                else:
                    node.setdefault(part, None)
            else:
                node = node.setdefault(part, {})

    lines: list[str] = []

    def sort_key(item: tuple[str, object]) -> tuple[int, str]:
        name, child = item
        # directories before files, important files near top
        important_rank = -1 if name in IMPORTANT_FILES else 0
        dir_rank = 0 if isinstance(child, dict) else 1
        return (important_rank, dir_rank, name.lower())

    def render(node: dict, prefix: str = "") -> None:
        if len(lines) >= max_lines:
            return
        items = sorted(node.items(), key=sort_key)
        for index, (name, child) in enumerate(items):
            if len(lines) >= max_lines:
                lines.append("...")
                return
            connector = "`-- " if index == len(items) - 1 else "|-- "
            lines.append(prefix + connector + name + ("/" if isinstance(child, dict) else ""))
            if isinstance(child, dict):
                extension = "    " if index == len(items) - 1 else "|   "
                render(child, prefix + extension)

    render(tree)
    return lines


def top_level_modules(files: Sequence[str], limit: int = 30) -> list[str]:
    seen: dict[str, int] = defaultdict(int)
    root_files: list[str] = []
    for rel in files:
        parts = rel.split("/")
        if len(parts) == 1:
            if parts[0] in IMPORTANT_FILES:
                root_files.append(parts[0])
        else:
            seen[parts[0]] += 1
    modules = [f"{name}/ ({count} files)" for name, count in sorted(seen.items(), key=lambda x: (-x[1], x[0]))[:limit]]
    if root_files:
        modules.extend(sorted(root_files)[:10])
    return modules


def git_changed_files(root: Path, max_files: int = 80) -> list[str]:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), "status", "--short"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
        )
    except Exception:
        return []
    changed: list[str] = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        # Porcelain v1: XY path OR XY old -> new
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1].strip()
        if path:
            changed.append(path)
        if len(changed) >= max_files:
            break
    return changed


def write_build(root: Path, quiet: bool = False) -> None:
    ctx = context_dir(root)
    ctx.mkdir(parents=True, exist_ok=True)
    ignore_dirs, ignore_globs = load_custom_ignore(root)
    files = collect_files(root)
    file_hash = sha256_lines(files)
    config_hash = index_config_hash(ignore_dirs, ignore_globs)
    meta_path = ctx / "tree-meta.json"
    old_meta: dict[str, object] = {}
    if meta_path.exists():
        try:
            old_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            old_meta = {}

    # Rewrite when paths, rendering rules, ignore rules, or schema change.
    if (
        old_meta.get("file_hash") == file_hash
        and old_meta.get("config_hash") == config_hash
        and old_meta.get("schema") == INDEX_SCHEMA
        and (ctx / "project-files.txt").exists()
        and (ctx / "project-tree.md").exists()
    ):
        if not quiet:
            print("Tree context is already up to date.")
        return

    write_text_atomic(ctx / "project-files.txt", "\n".join(files) + ("\n" if files else ""))

    tree_lines = build_tree_lines(files)
    modules = top_level_modules(files)
    md = []
    md.append("# Project Tree Index")
    md.append("")
    md.append(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    md.append(f"Files indexed: {len(files)}")
    md.append("")
    md.append("## Top-level modules")
    for item in modules:
        md.append(f"- {item}")
    md.append("")
    md.append("## Compact tree")
    md.append("```text")
    md.extend(tree_lines)
    md.append("```")
    write_text_atomic(ctx / "project-tree.md", "\n".join(md) + "\n")

    meta = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "file_count": len(files),
        "file_hash": file_hash,
        "config_hash": config_hash,
        "render_version": RENDER_VERSION,
        "root": str(root),
        "schema": INDEX_SCHEMA,
    }
    write_text_atomic(meta_path, json.dumps(meta, ensure_ascii=False, indent=2) + "\n")
    if not quiet:
        print(f"Tree context updated: {len(files)} files indexed.")

def index_is_stale(root: Path) -> bool:
    ctx = context_dir(root)
    meta_path = ctx / "tree-meta.json"
    if not (ctx / "project-files.txt").exists() or not (ctx / "project-tree.md").exists() or not meta_path.exists():
        return True
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        ignore_dirs, ignore_globs = load_custom_ignore(root)
        files = collect_files(root)
        return not (
            meta.get("file_hash") == sha256_lines(files)
            and meta.get("config_hash") == index_config_hash(ignore_dirs, ignore_globs)
            and meta.get("schema") == INDEX_SCHEMA
        )
    except Exception:
        return True


def ensure_built(root: Path) -> None:
    if index_is_stale(root):
        write_build(root, quiet=True)


def read_files_index(root: Path) -> list[str]:
    ensure_built(root)
    path = context_dir(root) / "project-files.txt"
    if not path.exists():
        return []
    return [line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines() if line.strip()]


def extract_keywords(prompt: str) -> list[str]:
    prompt_l = prompt.lower()
    words = set(re.findall(r"[a-zA-Z_][a-zA-Z0-9_\-]{1,}", prompt_l))
    # common words that are not useful for path matching
    stop = {
        "the", "and", "for", "with", "this", "that", "from", "into", "code", "file", "files",
        "help", "fix", "add", "new", "use", "using", "error", "bug", "project", "please",
        "claude", "code", "token", "tokens",
    }
    words -= stop
    expanded = set(words)
    for zh, vals in SYNONYMS.items():
        if zh in prompt:
            expanded.update(vals)
    # Include quoted path-like tokens.
    for quoted in re.findall(r"[`'\"]([^`'\"]+)[`'\"]", prompt):
        if any(ch in quoted for ch in "/\\."):
            expanded.add(quoted.lower().replace("\\", "/"))
    return sorted(expanded, key=lambda x: (-len(x), x))[:40]


def score_file(rel: str, keywords: Sequence[str], changed: set[str]) -> int:
    lower = rel.lower()
    base = lower.rsplit("/", 1)[-1]
    stem = base.rsplit(".", 1)[0]
    score = 0
    if rel in changed:
        score += 40
    if Path(rel).name in IMPORTANT_FILES:
        score += 6
    ext = Path(rel).suffix.lower()
    if ext in CODE_EXTS:
        score += 2
    for kw in keywords:
        if not kw:
            continue
        if "/" in kw or "." in kw:
            if kw in lower:
                score += 30
        elif kw == stem:
            score += 25
        elif kw in base:
            score += 18
        elif f"/{kw}" in lower or f"{kw}/" in lower:
            score += 14
        elif kw in lower:
            score += 8
    # Prefer source/config paths over docs/assets when scores are equal.
    if any(part in lower.split("/") for part in ["src", "app", "server", "backend", "frontend", "api", "controllers", "services"]):
        score += 2
    if any(part in lower.split("/") for part in ["test", "tests", "spec", "__tests__"]):
        score += 1
    return score


def common_dirs(paths: Sequence[str], max_dirs: int = 18) -> list[str]:
    counts: dict[str, int] = defaultdict(int)
    for rel in paths:
        parts = rel.split("/")[:-1]
        for depth in range(1, min(4, len(parts)) + 1):
            counts["/".join(parts[:depth]) + "/"] += 1
    ranked = sorted(counts.items(), key=lambda x: (-x[1], len(x[0]), x[0]))
    return [d for d, _ in ranked[:max_dirs]]


def select_context(root: Path, prompt: str, max_candidates: int = 40, max_lines: int = 130) -> str:
    files = read_files_index(root)
    changed = set(git_changed_files(root))
    keywords = extract_keywords(prompt)

    scored = []
    for rel in files:
        s = score_file(rel, keywords, changed)
        if s > 0:
            scored.append((s, rel))
    scored.sort(key=lambda x: (-x[0], x[1]))
    candidates = [rel for _, rel in scored[:max_candidates]]

    # Ensure changed files are visible even if no keyword matched.
    for rel in sorted(changed):
        if rel in files and rel not in candidates:
            candidates.insert(0, rel)
    candidates = candidates[:max_candidates]

    roots = top_level_modules(files, limit=16)
    dirs = common_dirs(candidates)
    lines: list[str] = []
    lines.append("<tree-context compact=\"true\">")
    lines.append("Use this compact repository map before broad Grep/Glob. Prefer candidate files and directories first.")
    lines.append("")
    lines.append("## Root modules")
    for item in roots[:18]:
        lines.append(f"- {item}")

    if changed:
        lines.append("")
        lines.append("## Git changed/untracked files")
        for rel in sorted(changed)[:30]:
            lines.append(f"- {rel}")

    lines.append("")
    lines.append("## Prompt keywords used for path matching")
    lines.append("- " + (", ".join(keywords[:30]) if keywords else "none"))

    if dirs:
        lines.append("")
        lines.append("## Candidate directories")
        for d in dirs:
            lines.append(f"- {d}")

    lines.append("")
    lines.append("## Candidate files")
    if candidates:
        for rel in candidates:
            lines.append(f"- {rel}")
    else:
        lines.append("- No strong path match. Use root modules above, then run narrow Grep/Glob only if needed.")

    lines.append("")
    lines.append("## Token-saving rules for this turn")
    lines.append("- Read candidate files before running repository-wide Grep.")
    lines.append("- If Grep is needed, scope it to candidate directories when possible.")
    lines.append("- Do not read generated, dependency, build, binary, or log files unless explicitly required.")
    lines.append("- If creating, deleting, or moving files, the tree index will be refreshed by the PostToolUse hook.")
    lines.append("")
    lines.append("## Quality guardrails")
    lines.append("- Treat selected context as a starting point, not complete evidence.")
    lines.append("- Before editing, verify the relevant entry point, call site, or configuration path.")
    lines.append("- If candidates do not clearly match the task, run a narrow search from likely directories.")
    lines.append("- If behavior changes, check nearby tests or include a focused verification step.")
    lines.append("</tree-context>")

    if len(lines) > max_lines:
        lines = lines[: max_lines - 2] + ["...", "</tree-context>"]
    return "\n".join(lines) + "\n"

def read_hook_json_from_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {"prompt": raw}


def cmd_build(args: argparse.Namespace) -> int:
    write_build(project_root(args.root), quiet=args.quiet)
    return 0


def cmd_select(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    prompt = args.prompt or " ".join(args.prompt_args or [])
    print(select_context(root, prompt, args.max_candidates, args.max_lines), end="")
    return 0


def cmd_inject(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    data = read_hook_json_from_stdin()
    prompt = data.get("prompt", "") if isinstance(data, dict) else ""
    try:
        print(select_context(root, str(prompt), args.max_candidates, args.max_lines), end="")
    except Exception as exc:
        # Hooks should not break user prompts because the index failed.
        eprint(f"tree-context inject failed: {exc}")
        return 0
    return 0
MUTATING_BASH_RE = re.compile(
    r"(^|[;&|]\s*)(touch|mkdir|mv|cp|rm|ln|tee|install)\b|"
    r"(^|[^0-9])>>?|"
    r"\bgit\s+(mv|rm|checkout|switch|clean|apply|stash|pull|merge|reset)\b|"
    r"\b(npm|pnpm|yarn|bun)\s+(i|install|add|remove|rm)\b|"
    r"\b(go\s+mod\s+tidy|cargo\s+(add|remove)|dotnet\s+(add|remove))\b"
)

READ_ONLY_BASH_RE = re.compile(
    r"^\s*(rg|grep|find|ls|dir|cat|type|sed|awk|wc|head|tail|pwd|date)\b|"
    r"^\s*git\s+(status|diff|show|log|ls-files|rev-parse|branch)\b|"
    r"^\s*(python|python3|py)\b.*\s(--help|-h)\s*$|"
    r"^\s*(npm|pnpm|yarn|bun)\s+(test|run\s+(test|lint|typecheck|build))\b",
    re.IGNORECASE,
)


def find_hook_value(data: object, keys: set[str]) -> object | None:
    if isinstance(data, dict):
        for key, value in data.items():
            if key in keys:
                return value
        for value in data.values():
            found = find_hook_value(value, keys)
            if found is not None:
                return found
    elif isinstance(data, list):
        for item in data:
            found = find_hook_value(item, keys)
            if found is not None:
                return found
    return None


def should_rebuild_after_hook(data: dict) -> bool:
    if not data:
        return True
    tool_value = find_hook_value(data, {"tool_name", "tool", "name"})
    tool_name = str(tool_value or "").lower()
    if "bash" not in tool_name:
        return True

    command_value = find_hook_value(data, {"command", "cmd"})
    command = str(command_value or "").strip()
    if not command:
        return True
    if MUTATING_BASH_RE.search(command):
        return True
    if re.search(r"&&|\|\||;|\n", command):
        return True
    return not READ_ONLY_BASH_RE.search(command)

def cmd_post_update(args: argparse.Namespace) -> int:
    root = project_root(args.root)
    data = read_hook_json_from_stdin()
    try:
        if not should_rebuild_after_hook(data):
            return 0
        write_build(root, quiet=True)
    except Exception as exc:
        # Non-blocking. Avoid breaking Claude Code after file edits.
        eprint(f"tree-context update failed: {exc}")
        return 0
    return 0

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Claude Code compact project tree context")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_build = sub.add_parser("build", help="Build .claude/context project tree index")
    p_build.add_argument("--root", default=None)
    p_build.add_argument("--quiet", action="store_true")
    p_build.set_defaults(func=cmd_build)

    p_select = sub.add_parser("select", help="Print compact tree context for a prompt")
    p_select.add_argument("--root", default=None)
    p_select.add_argument("--prompt", default="")
    p_select.add_argument("--max-candidates", type=int, default=40)
    p_select.add_argument("--max-lines", type=int, default=130)
    p_select.add_argument("prompt_args", nargs="*")
    p_select.set_defaults(func=cmd_select)

    p_inject = sub.add_parser("inject", help="Read UserPromptSubmit JSON from stdin and print compact context")
    p_inject.add_argument("--root", default=None)
    p_inject.add_argument("--max-candidates", type=int, default=40)
    p_inject.add_argument("--max-lines", type=int, default=130)
    p_inject.set_defaults(func=cmd_inject)

    p_post = sub.add_parser("post-update", help="Rebuild index after file-changing tool use")
    p_post.add_argument("--root", default=None)
    p_post.set_defaults(func=cmd_post_update)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
