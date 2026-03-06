"""Everest sandbox diff via ./ev-cli and evsts CLI."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path


class EvCliError(Exception):
    pass


# --- ev-cli (local sandbox) ---


def _find_ev_cli(cwd: str) -> str:
    """Find the ev-cli script, walking up from cwd."""
    p = Path(cwd).resolve()
    for d in [p, *p.parents]:
        candidate = d / "ev-cli"
        if candidate.exists():
            return str(candidate)
    raise EvCliError(
        f"ev-cli not found in {cwd} or any parent directory. "
        "Make sure you're inside an Everest sandbox."
    )


def get_ev_diff(cwd: str = ".") -> str:
    """Run ./ev-cli diff full and return the output.

    Strips the npm/node preamble lines and deprecation warnings,
    returning from the 'info:' line onward.
    """
    ev_cli = _find_ev_cli(cwd)
    sandbox_root = str(Path(ev_cli).parent)

    result = subprocess.run(
        ["bash", ev_cli, "diff", "full"],
        cwd=sandbox_root,
        capture_output=True,
        text=True,
        timeout=120,
    )

    output = result.stdout
    if result.returncode != 0 and not output:
        raise EvCliError(result.stderr.strip() or "ev-cli diff full failed")

    # Strip npm/node preamble (> ev-cli, > node ..., DeprecationWarning lines)
    lines = output.split("\n")
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("info:"):
            start = i
            break
    return "\n".join(lines[start:])


def get_sandbox_root(cwd: str = ".") -> str:
    """Return the Everest sandbox root (directory containing ev-cli)."""
    ev_cli = _find_ev_cli(cwd)
    return str(Path(ev_cli).parent)


# --- evsts sandbox diff (remote, by sandbox ID) ---

# ANSI escape sequence pattern
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")


def get_evsts_sandbox_diff(sandbox_id: int) -> str:
    """Run `evsts sandbox diff <id> --no-color` and return the unified diff.

    Strips the progress/spinner lines, returning from the first 'diff --git'
    line onward.
    """
    result = subprocess.run(
        ["evsts", "sandbox", "diff", str(sandbox_id), "--no-color"],
        capture_output=True,
        text=True,
        timeout=120,
    )

    output = result.stdout
    if result.returncode != 0 and not output:
        raise EvCliError(result.stderr.strip() or f"evsts sandbox diff {sandbox_id} failed")

    # Strip any residual ANSI codes
    output = _ANSI_RE.sub("", output)

    # Skip progress lines until the first diff header
    lines = output.split("\n")
    start = 0
    for i, line in enumerate(lines):
        if line.startswith("diff --git"):
            start = i
            break
    return "\n".join(lines[start:])
