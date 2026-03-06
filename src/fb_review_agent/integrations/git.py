"""Git operations via subprocess."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(Exception):
    pass


def _run(args: list[str], cwd: str) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise GitError(result.stderr.strip())
    return result.stdout


def get_repo_root(path: str = ".") -> str:
    """Find the git repo root from the given path."""
    return _run(["rev-parse", "--show-toplevel"], cwd=path).strip()


def get_diff(revision: str = "HEAD~1..HEAD", cwd: str = ".") -> str:
    """Get the unified diff for a revision range."""
    return _run(["diff", revision], cwd=cwd)


def get_current_branch(cwd: str = ".") -> str:
    """Get the current branch name."""
    return _run(["rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd).strip()


def get_merge_base(ref1: str, ref2: str, cwd: str = ".") -> str:
    """Get the merge base of two refs."""
    return _run(["merge-base", ref1, ref2], cwd=cwd).strip()


def is_git_repo(path: str = ".") -> bool:
    """Check if the given path is inside a git repository."""
    try:
        _run(["rev-parse", "--git-dir"], cwd=path)
        return True
    except (GitError, FileNotFoundError):
        return False
