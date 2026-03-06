"""GitHub PR operations via `gh` CLI."""

from __future__ import annotations

import json
import subprocess


class GhError(Exception):
    pass


def _run_gh(args: list[str], cwd: str = ".") -> str:
    result = subprocess.run(
        ["gh"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise GhError(result.stderr.strip())
    return result.stdout


def get_pr_diff(pr_number: int, cwd: str = ".") -> str:
    """Fetch the diff for a GitHub PR."""
    return _run_gh(["pr", "diff", str(pr_number)], cwd=cwd)


def get_pr_info(pr_number: int, cwd: str = ".") -> dict:
    """Fetch PR metadata (title, body, author, etc.)."""
    output = _run_gh(
        ["pr", "view", str(pr_number), "--json",
         "title,body,author,baseRefName,headRefName,url,number,additions,deletions,changedFiles"],
        cwd=cwd,
    )
    return json.loads(output)


def post_pr_comment(pr_number: int, body: str, cwd: str = ".") -> None:
    """Post a comment on a GitHub PR."""
    _run_gh(["pr", "comment", str(pr_number), "--body", body], cwd=cwd)
