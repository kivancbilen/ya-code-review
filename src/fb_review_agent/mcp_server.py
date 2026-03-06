"""MCP server — exposes fb-review tools via Model Context Protocol."""

from __future__ import annotations

import json
import os

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ya-code-review")


def _get_config():
    from fb_review_agent.config import Config
    return Config()


# --- Review tools ---


@mcp.tool()
def review_diff(diff_ref: str = "HEAD~1..HEAD", repo: str = ".", format: str = "markdown") -> str:
    """Review a git diff using semi-formal reasoning.

    Runs a multi-pass ensemble code review at 3 chunk granularities with deduplication.
    Returns structured findings with evidence chains.

    Args:
        diff_ref: Git revision range (e.g. "HEAD~1..HEAD", "main..feature")
        repo: Path to git repository
        format: Output format — "markdown", "json", or "terminal"
    """
    from fb_review_agent.integrations import git
    from fb_review_agent.review.orchestrator import review_diff as _review_diff
    from fb_review_agent.review.reporter import report_json, report_markdown

    config = _get_config()

    if not git.is_git_repo(repo):
        return "Error: Not a git repository."

    repo_root = git.get_repo_root(repo)
    diff_text = git.get_diff(diff_ref, cwd=repo_root)

    if not diff_text.strip():
        return "No changes found in the specified range."

    result = _review_diff(diff_text=diff_text, config=config, repo_root=repo_root)

    if format == "json":
        return report_json(result)
    return report_markdown(result)


@mcp.tool()
def review_sandbox(sandbox_id: int, repo: str = ".", format: str = "markdown") -> str:
    """Review an Everest sandbox by ID using semi-formal reasoning.

    Fetches the sandbox diff via evsts and runs the review agent.

    Args:
        sandbox_id: Everest sandbox ID (e.g. 464460)
        repo: Path to repo root for agent file exploration
        format: Output format — "markdown" or "json"
    """
    from fb_review_agent.integrations import everest, git
    from fb_review_agent.review.orchestrator import review_diff as _review_diff
    from fb_review_agent.review.reporter import report_json, report_markdown

    config = _get_config()
    diff_text = everest.get_evsts_sandbox_diff(sandbox_id)

    if not diff_text.strip():
        return "No changes found in sandbox."

    repo_root = repo
    if git.is_git_repo(repo):
        try:
            repo_root = git.get_repo_root(repo)
        except Exception:
            pass

    result = _review_diff(diff_text=diff_text, config=config, repo_root=repo_root)

    if format == "json":
        return report_json(result)
    return report_markdown(result)


@mcp.tool()
def review_ev_diff(sandbox_path: str = ".", format: str = "markdown") -> str:
    """Review local Everest sandbox changes using semi-formal reasoning.

    Runs ev-cli diff full from the sandbox directory and reviews the changes.

    Args:
        sandbox_path: Path to Everest sandbox (must contain ev-cli)
        format: Output format — "markdown" or "json"
    """
    from fb_review_agent.integrations import everest
    from fb_review_agent.review.orchestrator import review_diff as _review_diff
    from fb_review_agent.review.reporter import report_json, report_markdown

    config = _get_config()
    sandbox_root = everest.get_sandbox_root(sandbox_path)
    diff_text = everest.get_ev_diff(sandbox_path)

    if not diff_text.strip():
        return "No changes found in the sandbox."

    result = _review_diff(diff_text=diff_text, config=config, repo_root=sandbox_root)

    if format == "json":
        return report_json(result)
    return report_markdown(result)


# --- Coverage tool ---


@mcp.tool()
def analyze_coverage(diff_ref: str = "HEAD~1..HEAD", repo: str = ".", format: str = "markdown") -> str:
    """Analyze test coverage for changed code (static analysis, no LLM calls).

    Extracts changed function/class names from diff, searches for test files,
    and reports coverage confidence per symbol.

    Args:
        diff_ref: Git revision range
        repo: Path to git repository
        format: Output format — "markdown" or "json"
    """
    from fb_review_agent.coverage.analyzer import analyze_coverage as _analyze
    from fb_review_agent.integrations import git
    from fb_review_agent.review.diff_parser import parse_diff
    from fb_review_agent.review.reporter import report_coverage_markdown

    if not git.is_git_repo(repo):
        return "Error: Not a git repository."

    repo_root = git.get_repo_root(repo)
    diff_text = git.get_diff(diff_ref, cwd=repo_root)

    if not diff_text.strip():
        return "No changes found."

    parsed = parse_diff(diff_text)
    report = _analyze(parsed.files, repo_root)

    if format == "json":
        data = {
            "coverage_ratio": report.coverage_ratio,
            "mappings": [
                {
                    "symbol": m.symbol.name,
                    "file": m.symbol.file,
                    "confidence": m.confidence,
                    "test_files": m.test_files,
                }
                for m in report.mappings
            ],
            "uncovered_symbols": [
                {"name": s.name, "file": s.file}
                for s in report.uncovered_symbols
            ],
        }
        return json.dumps(data, indent=2)
    return report_coverage_markdown(report)


# --- Fault localization tool ---


@mcp.tool()
def fault_localize(
    bug_description: str,
    repo: str = ".",
    diff_ref: str | None = None,
    format: str = "markdown",
) -> str:
    """Localize a fault using semi-formal reasoning.

    Uses a 5-phase methodology to systematically identify suspect code
    locations for a described bug.

    Args:
        bug_description: Description of the bug (error messages, symptoms, etc.)
        repo: Path to git repository
        diff_ref: Optional git revision range to limit search to changed files
        format: Output format — "markdown" or "json"
    """
    from fb_review_agent.fault.localize import run_fault_localization
    from fb_review_agent.integrations import git

    config = _get_config()
    repo_root = repo
    if git.is_git_repo(repo):
        try:
            repo_root = git.get_repo_root(repo)
        except Exception:
            pass

    result = run_fault_localization(
        bug_description=bug_description,
        config=config,
        repo_root=repo_root,
        diff_ref=diff_ref,
    )

    if format == "json":
        data = {
            "suspects": [
                {
                    "file": s.file,
                    "line_start": s.line_start,
                    "line_end": s.line_end,
                    "suspicion_score": s.suspicion_score,
                    "hypothesis": s.hypothesis,
                    "evidence": s.evidence,
                }
                for s in result.suspects
            ],
            "reasoning_log": result.reasoning_log,
        }
        return json.dumps(data, indent=2)

    lines = ["# Fault Localization Report\n"]
    if not result.suspects:
        lines.append("No suspect locations identified.\n")
    else:
        for i, s in enumerate(result.suspects, 1):
            score_pct = f"{s.suspicion_score * 100:.0f}%"
            lines.append(f"## #{i} — {s.file}:{s.line_start}-{s.line_end} (score: {score_pct})\n")
            lines.append(f"**Hypothesis:** {s.hypothesis}\n")
            if s.evidence:
                lines.append("**Evidence:**")
                for e in s.evidence:
                    lines.append(f"- {e}")
                lines.append("")
    if result.reasoning_log:
        lines.append(f"---\n\n{result.reasoning_log}")
    return "\n".join(lines)


# --- Patch equivalence tool ---


@mcp.tool()
def patch_equivalence(
    patch_a: str,
    patch_b: str,
    repo: str = ".",
    format: str = "markdown",
) -> str:
    """Compare two patches for behavioral equivalence.

    Uses a 5-phase methodology to systematically analyze whether two patches
    produce the same observable behavior.

    Args:
        patch_a: First diff text
        patch_b: Second diff text
        repo: Path to git repository for code exploration
        format: Output format — "markdown" or "json"
    """
    from fb_review_agent.equivalence.compare import run_patch_equivalence
    from fb_review_agent.integrations import git

    config = _get_config()
    repo_root = repo
    if git.is_git_repo(repo):
        try:
            repo_root = git.get_repo_root(repo)
        except Exception:
            pass

    result = run_patch_equivalence(
        patch_a=patch_a,
        patch_b=patch_b,
        config=config,
        repo_root=repo_root,
    )

    if format == "json":
        data = {
            "verdict": result.verdict.value,
            "confidence": result.confidence,
            "differences": [
                {
                    "description": d.description,
                    "input_that_differs": d.input_that_differs,
                    "patch_a_behavior": d.patch_a_behavior,
                    "patch_b_behavior": d.patch_b_behavior,
                    "severity": d.severity,
                }
                for d in result.differences
            ],
            "reasoning_log": result.reasoning_log,
        }
        return json.dumps(data, indent=2)

    lines = [f"# Patch Equivalence Report\n"]
    lines.append(f"**Verdict:** {result.verdict.value} | **Confidence:** {result.confidence}\n")
    if result.differences:
        lines.append("## Behavioral Differences\n")
        for i, d in enumerate(result.differences, 1):
            lines.append(f"### #{i}: {d.description}\n")
            lines.append(f"- **Severity:** {d.severity}")
            lines.append(f"- **Diverging input:** {d.input_that_differs}")
            lines.append(f"- **Patch A:** {d.patch_a_behavior}")
            lines.append(f"- **Patch B:** {d.patch_b_behavior}\n")
    else:
        lines.append("No behavioral differences found.\n")
    return "\n".join(lines)


# --- Memory tools ---


@mcp.tool()
def memory_list() -> str:
    """List all known review patterns from the memory store."""
    from fb_review_agent.memory.store import PatternStore

    config = _get_config()
    store = PatternStore(config.get_memory_path())
    patterns = store.list_all()

    if not patterns:
        return "No patterns stored."

    lines = ["# Known Review Patterns\n"]
    lines.append("| ID | Pattern | Severity | Category | File Patterns | Hits |")
    lines.append("|----|---------|----------|----------|---------------|------|")
    for p in patterns:
        files = ", ".join(p.file_patterns) if p.file_patterns else "*"
        lines.append(f"| {p.id} | {p.pattern} | {p.severity} | {p.category} | {files} | {p.hit_count} |")
    return "\n".join(lines)


@mcp.tool()
def memory_add(
    pattern: str,
    description: str,
    severity: str = "medium",
    category: str = "correctness",
    file_patterns: list[str] | None = None,
    example_snippet: str = "",
) -> str:
    """Add a new known pattern to the review memory store.

    Args:
        pattern: Short pattern description
        description: Detailed explanation
        severity: Default severity (critical/high/medium/low)
        category: Category (correctness/performance/security/style/maintainability/concurrency)
        file_patterns: Glob patterns for matching files (e.g. ["*.py", "src/api/**"])
        example_snippet: Representative code example
    """
    from fb_review_agent.memory.store import KnownPattern, PatternStore

    config = _get_config()
    store = PatternStore(config.get_memory_path())

    kp = KnownPattern(
        id="",
        pattern=pattern,
        description=description,
        severity=severity,
        category=category,
        file_patterns=file_patterns or [],
        example_snippet=example_snippet,
    )
    store.add(kp)
    return f"Added pattern {kp.id}: {pattern}"


@mcp.tool()
def memory_remove(pattern_id: str) -> str:
    """Remove a known pattern from the memory store by ID.

    Args:
        pattern_id: Pattern ID to remove (e.g. "P001")
    """
    from fb_review_agent.memory.store import PatternStore

    config = _get_config()
    store = PatternStore(config.get_memory_path())

    if store.remove(pattern_id):
        return f"Removed pattern {pattern_id}"
    return f"Pattern {pattern_id} not found"


def main():
    """Run the MCP server via stdio."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
