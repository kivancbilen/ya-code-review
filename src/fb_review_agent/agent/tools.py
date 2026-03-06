"""Tool definitions and dispatch for the agent loop."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": (
            "Read the contents of a file at the given path. "
            "Use this to examine source code, configuration, or any text file. "
            "Returns the full file content with line numbers."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or repo-relative path to the file.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional 1-based start line to read from.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional 1-based end line to read to (inclusive).",
                },
            },
            "required": ["path"],
        },
    },
    {
        "name": "grep_search",
        "description": (
            "Search for a pattern across files using regex. "
            "Returns matching lines with file paths and line numbers. "
            "Use this to find callers, references, definitions, and patterns."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Regex pattern to search for.",
                },
                "path": {
                    "type": "string",
                    "description": "Directory or file to search in. Defaults to repo root.",
                },
                "include": {
                    "type": "string",
                    "description": "Glob pattern for files to include (e.g. '*.py').",
                },
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "list_files",
        "description": (
            "List files and directories at the given path. "
            "Use this to understand project structure."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directory to list. Defaults to repo root.",
                },
                "recursive": {
                    "type": "boolean",
                    "description": "If true, list recursively. Default false.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "git_diff",
        "description": (
            "Get the git diff for a given revision range. "
            "Returns unified diff output."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "revision": {
                    "type": "string",
                    "description": "Revision range (e.g. 'HEAD~1..HEAD', 'main..feature').",
                },
                "path": {
                    "type": "string",
                    "description": "Optional file path to limit the diff to.",
                },
            },
            "required": ["revision"],
        },
    },
    {
        "name": "git_log",
        "description": (
            "Get git log entries for a given revision range or file. "
            "Returns commit hash, author, date, and message."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "revision": {
                    "type": "string",
                    "description": "Revision range or ref (e.g. 'HEAD~5..HEAD', 'main').",
                },
                "path": {
                    "type": "string",
                    "description": "Optional file path to limit log to.",
                },
                "max_count": {
                    "type": "integer",
                    "description": "Maximum number of log entries. Default 10.",
                },
            },
            "required": [],
        },
    },
    {
        "name": "git_blame",
        "description": (
            "Get git blame output for a file, showing who last modified each line. "
            "Use this to understand change history for specific code sections."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file to blame.",
                },
                "start_line": {
                    "type": "integer",
                    "description": "Optional 1-based start line.",
                },
                "end_line": {
                    "type": "integer",
                    "description": "Optional 1-based end line.",
                },
            },
            "required": ["path"],
        },
    },
]


def _resolve_path(path: str | None, repo_root: str) -> str:
    """Resolve a path relative to the repo root."""
    if not path:
        return repo_root
    p = Path(path)
    if p.is_absolute():
        return str(p)
    return str(Path(repo_root) / p)


def _run_git(args: list[str], cwd: str) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        return f"Error: {result.stderr.strip()}"
    return result.stdout


def dispatch_tool(name: str, input: dict, repo_root: str) -> str:
    """Execute a tool and return its string result."""
    try:
        if name == "read_file":
            return _tool_read_file(input, repo_root)
        elif name == "grep_search":
            return _tool_grep_search(input, repo_root)
        elif name == "list_files":
            return _tool_list_files(input, repo_root)
        elif name == "git_diff":
            return _tool_git_diff(input, repo_root)
        elif name == "git_log":
            return _tool_git_log(input, repo_root)
        elif name == "git_blame":
            return _tool_git_blame(input, repo_root)
        else:
            return f"Error: Unknown tool '{name}'"
    except Exception as e:
        return f"Error executing {name}: {e}"


def _tool_read_file(input: dict, repo_root: str) -> str:
    path = _resolve_path(input["path"], repo_root)
    try:
        with open(path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        return f"Error: File not found: {path}"
    except IsADirectoryError:
        return f"Error: Path is a directory: {path}"

    start = input.get("start_line", 1)
    end = input.get("end_line", len(lines))
    start = max(1, start)
    end = min(len(lines), end)

    numbered = []
    for i in range(start - 1, end):
        numbered.append(f"{i + 1:>6}\t{lines[i].rstrip()}")

    if not numbered:
        return "(empty file)"
    return "\n".join(numbered)


def _tool_grep_search(input: dict, repo_root: str) -> str:
    path = _resolve_path(input.get("path"), repo_root)
    args = ["grep", "-rn", "--color=never"]
    include = input.get("include")
    if include:
        args.extend(["--include", include])
    args.extend([input["pattern"], path])

    result = subprocess.run(
        args, capture_output=True, text=True, timeout=30
    )
    output = result.stdout.strip()
    if not output:
        return "(no matches)"

    # Limit output to avoid blowing up context
    lines = output.split("\n")
    if len(lines) > 100:
        return "\n".join(lines[:100]) + f"\n... ({len(lines) - 100} more matches)"
    return output


def _tool_list_files(input: dict, repo_root: str) -> str:
    path = _resolve_path(input.get("path"), repo_root)
    recursive = input.get("recursive", False)

    try:
        p = Path(path)
        if not p.is_dir():
            return f"Error: Not a directory: {path}"

        if recursive:
            entries = sorted(str(e.relative_to(p)) for e in p.rglob("*") if not any(
                part.startswith(".") for part in e.relative_to(p).parts
            ))
        else:
            entries = sorted(
                f"{'/' if e.is_dir() else ''}{e.name}" for e in p.iterdir()
                if not e.name.startswith(".")
            )

        if not entries:
            return "(empty directory)"
        if len(entries) > 200:
            return "\n".join(entries[:200]) + f"\n... ({len(entries) - 200} more entries)"
        return "\n".join(entries)
    except Exception as e:
        return f"Error: {e}"


def _tool_git_diff(input: dict, repo_root: str) -> str:
    args = ["diff", input["revision"]]
    path = input.get("path")
    if path:
        args.extend(["--", _resolve_path(path, repo_root)])
    return _run_git(args, repo_root) or "(no diff)"


def _tool_git_log(input: dict, repo_root: str) -> str:
    max_count = input.get("max_count", 10)
    args = ["log", f"--max-count={max_count}", "--format=%H %an %ad %s", "--date=short"]
    revision = input.get("revision")
    if revision:
        args.append(revision)
    path = input.get("path")
    if path:
        args.extend(["--", _resolve_path(path, repo_root)])
    return _run_git(args, repo_root) or "(no log entries)"


def _tool_git_blame(input: dict, repo_root: str) -> str:
    path = _resolve_path(input["path"], repo_root)
    args = ["blame", "--date=short"]
    start = input.get("start_line")
    end = input.get("end_line")
    if start and end:
        args.extend([f"-L{start},{end}"])
    elif start:
        args.extend([f"-L{start},"])
    args.append(path)
    return _run_git(args, repo_root) or "(no blame output)"
