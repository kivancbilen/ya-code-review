"""CLI entry point: review, pr, sandbox, ev-diff, memory, coverage, fault-localize, patch-equiv."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console

from fb_review_agent.config import Config
from fb_review_agent.integrations import everest, git, github
from fb_review_agent.review.finding import ReviewResult
from fb_review_agent.review.orchestrator import review_diff
from fb_review_agent.review.reporter import report_json, report_markdown, report_terminal


console = Console(stderr=True)


def _tool_call_callback(name: str, input: dict) -> None:
    """Print tool calls to stderr for visibility."""
    detail = ""
    if name == "read_file":
        detail = input.get("path", "")
    elif name == "grep_search":
        detail = input.get("pattern", "")
    elif name == "list_files":
        detail = input.get("path", ".")
    elif name in ("git_diff", "git_log"):
        detail = input.get("revision", "")
    elif name == "git_blame":
        detail = input.get("path", "")
    console.print(f"  [dim]→ {name}({detail})[/dim]")


def _output_result(result: ReviewResult, output_format: str, verbose: bool) -> None:
    """Render review results in the chosen format."""
    if output_format == "terminal":
        report_terminal(result, console=Console(), verbose=verbose)
    elif output_format == "markdown":
        click.echo(report_markdown(result))
    elif output_format == "json":
        click.echo(report_json(result))


def _run_coverage_if_requested(coverage: bool, diff_text: str, repo_root: str, output_format: str) -> None:
    """Run coverage analysis and output if --coverage flag is set."""
    if not coverage:
        return

    from fb_review_agent.coverage.analyzer import analyze_coverage
    from fb_review_agent.review.diff_parser import parse_diff
    from fb_review_agent.review.reporter import report_coverage_markdown, report_coverage_terminal

    parsed = parse_diff(diff_text)
    if not parsed.files:
        return

    console.print("\n[bold blue]Running test coverage analysis...[/bold blue]")
    report = analyze_coverage(parsed.files, repo_root)

    if output_format == "terminal":
        report_coverage_terminal(report, console=Console())
    elif output_format == "markdown":
        click.echo(report_coverage_markdown(report))
    elif output_format == "json":
        data = {
            "coverage_ratio": report.coverage_ratio,
            "mappings": [
                {
                    "symbol": m.symbol.name,
                    "file": m.symbol.file,
                    "line_start": m.symbol.line_start,
                    "line_end": m.symbol.line_end,
                    "confidence": m.confidence,
                    "test_files": m.test_files,
                }
                for m in report.mappings
            ],
            "uncovered_symbols": [
                {"name": s.name, "file": s.file, "line_start": s.line_start}
                for s in report.uncovered_symbols
            ],
        }
        click.echo(json.dumps(data, indent=2))


@click.group()
@click.option("--model", default=None, help="Override model (default: claude-opus-4-6)")
@click.option("--max-turns", default=None, type=int, help="Max agent turns (default: 40)")
@click.pass_context
def cli(ctx: click.Context, model: str | None, max_turns: int | None) -> None:
    """fb-review — Semi-formal reasoning code review agent."""
    config = Config()
    if model:
        config.model = model
    if max_turns:
        config.max_turns = max_turns
    ctx.ensure_object(dict)
    ctx.obj["config"] = config


@cli.command()
@click.argument("diff_ref", default="HEAD~1..HEAD")
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--verbose", "-v", is_flag=True, help="Show reasoning log")
@click.option("--repo", default=".", help="Path to git repository")
@click.option("--coverage", is_flag=True, help="Run test coverage analysis")
def review(diff_ref: str, output_format: str, verbose: bool, repo: str, coverage: bool) -> None:
    """Review a git diff using semi-formal reasoning.

    DIFF_REF is a git revision range (default: HEAD~1..HEAD).
    Examples: HEAD~3..HEAD, main..feature, abc123..def456
    """
    config: Config = click.get_current_context().obj["config"]

    if not git.is_git_repo(repo):
        console.print("[red]Error:[/red] Not a git repository.")
        sys.exit(1)

    repo_root = git.get_repo_root(repo)

    console.print(f"[bold]Reviewing diff: {diff_ref}[/bold]")
    console.print(f"[dim]Model: {config.model} | Max turns: {config.max_turns}[/dim]\n")

    try:
        diff_text = git.get_diff(diff_ref, cwd=repo_root)
    except git.GitError as e:
        console.print(f"[red]Git error:[/red] {e}")
        sys.exit(1)

    if not diff_text.strip():
        console.print("[yellow]No changes found in the specified range.[/yellow]")
        sys.exit(0)

    result = review_diff(
        diff_text=diff_text,
        config=config,
        repo_root=repo_root,
        on_tool_call=_tool_call_callback,
    )
    _output_result(result, output_format, verbose)
    _run_coverage_if_requested(coverage, diff_text, repo_root, output_format)


@cli.command()
@click.argument("pr_number", type=int)
@click.option("--comment", is_flag=True, help="Post review as PR comment")
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--verbose", "-v", is_flag=True, help="Show reasoning log")
@click.option("--repo", default=".", help="Path to git repository")
@click.option("--coverage", is_flag=True, help="Run test coverage analysis")
def pr(pr_number: int, comment: bool, output_format: str, verbose: bool, repo: str, coverage: bool) -> None:
    """Review a GitHub PR using semi-formal reasoning.

    Fetches the PR diff via `gh` CLI and runs the review agent.
    """
    config: Config = click.get_current_context().obj["config"]

    if not git.is_git_repo(repo):
        console.print("[red]Error:[/red] Not a git repository.")
        sys.exit(1)

    repo_root = git.get_repo_root(repo)

    try:
        pr_info = github.get_pr_info(pr_number, cwd=repo_root)
    except github.GhError as e:
        console.print(f"[red]GitHub error:[/red] {e}")
        sys.exit(1)

    console.print(f"[bold]Reviewing PR #{pr_number}: {pr_info['title']}[/bold]")
    console.print(f"[dim]{pr_info['baseRefName']} ← {pr_info['headRefName']}[/dim]")
    console.print(f"[dim]Model: {config.model} | Max turns: {config.max_turns}[/dim]\n")

    try:
        diff_text = github.get_pr_diff(pr_number, cwd=repo_root)
    except github.GhError as e:
        console.print(f"[red]GitHub error:[/red] {e}")
        sys.exit(1)

    if not diff_text.strip():
        console.print("[yellow]PR has no changes.[/yellow]")
        sys.exit(0)

    result = review_diff(
        diff_text=diff_text,
        config=config,
        repo_root=repo_root,
        on_tool_call=_tool_call_callback,
    )
    _output_result(result, output_format, verbose)
    _run_coverage_if_requested(coverage, diff_text, repo_root, output_format)

    if comment:
        md = report_markdown(result)
        try:
            github.post_pr_comment(pr_number, md, cwd=repo_root)
            console.print(f"\n[green]Review posted as comment on PR #{pr_number}[/green]")
        except github.GhError as e:
            console.print(f"\n[red]Failed to post comment:[/red] {e}")
            sys.exit(1)


@cli.command()
@click.argument("sandbox_id", type=int)
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--verbose", "-v", is_flag=True, help="Show reasoning log")
@click.option("--repo", default=".", help="Path to repo root for agent file exploration")
@click.option("--coverage", is_flag=True, help="Run test coverage analysis")
def sandbox(sandbox_id: int, output_format: str, verbose: bool, repo: str, coverage: bool) -> None:
    """Review an Everest sandbox by ID using semi-formal reasoning.

    Fetches the diff via `evsts sandbox diff <SANDBOX_ID>` and reviews it.

    Example: fb-review sandbox 464460
    """
    config: Config = click.get_current_context().obj["config"]

    console.print(f"[bold]Reviewing Everest sandbox {sandbox_id}[/bold]")
    console.print(f"[dim]Model: {config.model} | Max turns: {config.max_turns}[/dim]\n")

    console.print(f"[dim]Running evsts sandbox diff {sandbox_id}...[/dim]")
    try:
        diff_text = everest.get_evsts_sandbox_diff(sandbox_id)
    except everest.EvCliError as e:
        console.print(f"[red]evsts error:[/red] {e}")
        sys.exit(1)

    if not diff_text.strip():
        console.print("[yellow]No changes found in sandbox.[/yellow]")
        sys.exit(0)

    repo_root = repo
    if git.is_git_repo(repo):
        try:
            repo_root = git.get_repo_root(repo)
        except git.GitError:
            pass

    result = review_diff(
        diff_text=diff_text,
        config=config,
        repo_root=repo_root,
        on_tool_call=_tool_call_callback,
    )
    _output_result(result, output_format, verbose)
    _run_coverage_if_requested(coverage, diff_text, repo_root, output_format)


@cli.command("ev-diff")
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--verbose", "-v", is_flag=True, help="Show reasoning log")
@click.option("--sandbox", default=".", help="Path to Everest sandbox (must contain ev-cli)")
@click.option("--coverage", is_flag=True, help="Run test coverage analysis")
def ev_diff(output_format: str, verbose: bool, sandbox: str, coverage: bool) -> None:
    """Review local Everest sandbox changes using semi-formal reasoning.

    Runs ./ev-cli diff full to get the sandbox diff and reviews it.
    Must be run from within an Everest sandbox (or use --sandbox).
    """
    config: Config = click.get_current_context().obj["config"]

    try:
        sandbox_root = everest.get_sandbox_root(sandbox)
    except everest.EvCliError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    console.print(f"[bold]Reviewing Everest sandbox diff[/bold]")
    console.print(f"[dim]Sandbox: {sandbox_root}[/dim]")
    console.print(f"[dim]Model: {config.model} | Max turns: {config.max_turns}[/dim]\n")

    console.print("[dim]Running ev-cli diff full...[/dim]")
    try:
        diff_text = everest.get_ev_diff(sandbox)
    except everest.EvCliError as e:
        console.print(f"[red]ev-cli error:[/red] {e}")
        sys.exit(1)

    if not diff_text.strip():
        console.print("[yellow]No changes found in the sandbox.[/yellow]")
        sys.exit(0)

    result = review_diff(
        diff_text=diff_text,
        config=config,
        repo_root=sandbox_root,
        on_tool_call=_tool_call_callback,
    )
    _output_result(result, output_format, verbose)
    _run_coverage_if_requested(coverage, diff_text, sandbox_root, output_format)


# --- F7: Coverage standalone command ---

@cli.command()
@click.argument("diff_ref", default="HEAD~1..HEAD")
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--repo", default=".", help="Path to git repository")
def coverage(diff_ref: str, output_format: str, repo: str) -> None:
    """Analyze test coverage for changed code (no LLM calls).

    DIFF_REF is a git revision range (default: HEAD~1..HEAD).
    """
    from fb_review_agent.coverage.analyzer import analyze_coverage
    from fb_review_agent.review.diff_parser import parse_diff
    from fb_review_agent.review.reporter import report_coverage_markdown, report_coverage_terminal

    if not git.is_git_repo(repo):
        console.print("[red]Error:[/red] Not a git repository.")
        sys.exit(1)

    repo_root = git.get_repo_root(repo)

    try:
        diff_text = git.get_diff(diff_ref, cwd=repo_root)
    except git.GitError as e:
        console.print(f"[red]Git error:[/red] {e}")
        sys.exit(1)

    if not diff_text.strip():
        console.print("[yellow]No changes found.[/yellow]")
        sys.exit(0)

    parsed = parse_diff(diff_text)
    console.print(f"[bold]Analyzing test coverage for {diff_ref}[/bold]")
    console.print(f"[dim]{parsed.summary()}[/dim]\n")

    report = analyze_coverage(parsed.files, repo_root)

    if output_format == "terminal":
        report_coverage_terminal(report, console=Console())
    elif output_format == "markdown":
        click.echo(report_coverage_markdown(report))
    elif output_format == "json":
        data = {
            "coverage_ratio": report.coverage_ratio,
            "mappings": [
                {
                    "symbol": m.symbol.name,
                    "file": m.symbol.file,
                    "line_start": m.symbol.line_start,
                    "line_end": m.symbol.line_end,
                    "confidence": m.confidence,
                    "test_files": m.test_files,
                }
                for m in report.mappings
            ],
            "uncovered_symbols": [
                {"name": s.name, "file": s.file, "line_start": s.line_start}
                for s in report.uncovered_symbols
            ],
        }
        click.echo(json.dumps(data, indent=2))


# --- F3: Memory command group ---

@cli.group()
def memory() -> None:
    """Manage known review patterns (memory store)."""
    pass


@memory.command("list")
def memory_list() -> None:
    """List all known patterns."""
    from fb_review_agent.memory.store import PatternStore

    config: Config = click.get_current_context().obj["config"]
    store = PatternStore(config.get_memory_path())
    patterns = store.list_all()

    if not patterns:
        console.print("[dim]No patterns stored.[/dim]")
        console.print(f"[dim]Store location: {config.get_memory_path()}[/dim]")
        return

    out = Console()
    from rich.table import Table
    table = Table(title=f"Known Patterns ({len(patterns)})", show_lines=True)
    table.add_column("ID", width=6)
    table.add_column("Pattern", min_width=20)
    table.add_column("Severity", width=10)
    table.add_column("Category", width=14)
    table.add_column("File Patterns", min_width=15)
    table.add_column("Hits", width=5)

    for p in patterns:
        table.add_row(
            p.id,
            p.pattern,
            p.severity,
            p.category,
            ", ".join(p.file_patterns) if p.file_patterns else "*",
            str(p.hit_count),
        )

    out.print(table)


@memory.command("add")
@click.option("--pattern", "-p", required=True, help="Short pattern description")
@click.option("--description", "-d", required=True, help="Detailed explanation")
@click.option("--severity", "-s", type=click.Choice(["critical", "high", "medium", "low"]), default="medium")
@click.option("--category", "-c", type=click.Choice(["correctness", "performance", "security", "style", "maintainability", "concurrency"]), default="correctness")
@click.option("--files", "-f", multiple=True, help="File glob patterns (e.g. '*.py', 'src/api/**')")
@click.option("--example", "-e", default="", help="Example code snippet")
def memory_add(pattern: str, description: str, severity: str, category: str, files: tuple[str, ...], example: str) -> None:
    """Add a new known pattern."""
    from fb_review_agent.memory.store import KnownPattern, PatternStore

    config: Config = click.get_current_context().obj["config"]
    store = PatternStore(config.get_memory_path())

    kp = KnownPattern(
        id="",  # auto-assigned
        pattern=pattern,
        description=description,
        severity=severity,
        category=category,
        file_patterns=list(files),
        example_snippet=example,
    )
    store.add(kp)
    console.print(f"[green]Added pattern {kp.id}: {pattern}[/green]")


@memory.command("remove")
@click.argument("pattern_id")
def memory_remove(pattern_id: str) -> None:
    """Remove a known pattern by ID."""
    from fb_review_agent.memory.store import PatternStore

    config: Config = click.get_current_context().obj["config"]
    store = PatternStore(config.get_memory_path())

    if store.remove(pattern_id):
        console.print(f"[green]Removed pattern {pattern_id}[/green]")
    else:
        console.print(f"[red]Pattern {pattern_id} not found[/red]")
        sys.exit(1)


@memory.command("export")
@click.option("--output", "-o", default="-", help="Output file (default: stdout)")
def memory_export(output: str) -> None:
    """Export patterns to JSON."""
    from fb_review_agent.memory.store import PatternStore

    config: Config = click.get_current_context().obj["config"]
    store = PatternStore(config.get_memory_path())
    json_text = store.export_json()

    if output == "-":
        click.echo(json_text)
    else:
        Path(output).write_text(json_text)
        console.print(f"[green]Exported to {output}[/green]")


@memory.command("import")
@click.argument("file", type=click.Path(exists=True))
def memory_import(file: str) -> None:
    """Import patterns from a JSON file."""
    from fb_review_agent.memory.store import PatternStore

    config: Config = click.get_current_context().obj["config"]
    store = PatternStore(config.get_memory_path())
    json_text = Path(file).read_text()
    count = store.import_json(json_text)
    console.print(f"[green]Imported {count} new pattern(s)[/green]")


# --- F8: Fault localization command ---

@cli.command("fault-localize")
@click.argument("description")
@click.option("--diff-ref", default=None, help="Limit search to files changed in this diff range")
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--verbose", "-v", is_flag=True, help="Show reasoning log")
@click.option("--repo", default=".", help="Path to git repository")
def fault_localize(description: str, diff_ref: str | None, output_format: str, verbose: bool, repo: str) -> None:
    """Localize a fault using semi-formal reasoning.

    DESCRIPTION is a text description of the bug (error messages, symptoms, etc).

    Example: fb-review fault-localize "TypeError in handler when request body is empty"
    """
    from fb_review_agent.fault.localize import run_fault_localization

    config: Config = click.get_current_context().obj["config"]
    repo_root = repo
    if git.is_git_repo(repo):
        try:
            repo_root = git.get_repo_root(repo)
        except git.GitError:
            pass

    console.print(f"[bold]Fault localization: {description[:80]}{'...' if len(description) > 80 else ''}[/bold]")
    if diff_ref:
        console.print(f"[dim]Limiting to changes in: {diff_ref}[/dim]")
    console.print(f"[dim]Model: {config.model} | Max turns: {config.max_turns}[/dim]\n")

    result = run_fault_localization(
        bug_description=description,
        config=config,
        repo_root=repo_root,
        diff_ref=diff_ref,
        on_tool_call=_tool_call_callback,
    )

    if output_format == "terminal":
        _report_fault_terminal(result, verbose)
    elif output_format == "markdown":
        click.echo(_report_fault_markdown(result))
    elif output_format == "json":
        click.echo(_report_fault_json(result))


def _report_fault_terminal(result, verbose: bool) -> None:
    from rich.panel import Panel
    from rich.table import Table

    out = Console()

    if not result.suspects:
        out.print("[yellow]No suspect locations identified.[/yellow]")
        if verbose and result.reasoning_log:
            out.print(Panel(result.reasoning_log, title="Reasoning Log", border_style="dim"))
        return

    table = Table(title="Suspect Locations", show_lines=True)
    table.add_column("#", width=3)
    table.add_column("Score", width=6)
    table.add_column("File", min_width=20)
    table.add_column("Lines", width=10)
    table.add_column("Hypothesis", min_width=30)

    for i, s in enumerate(result.suspects, 1):
        score_pct = f"{s.suspicion_score * 100:.0f}%"
        style = "red" if s.suspicion_score > 0.7 else "yellow" if s.suspicion_score > 0.4 else "blue"
        table.add_row(
            str(i),
            f"[{style}]{score_pct}[/{style}]",
            s.file,
            f"{s.line_start}-{s.line_end}",
            s.hypothesis,
        )

    out.print(table)

    for i, s in enumerate(result.suspects, 1):
        if s.evidence:
            out.print(f"\n[bold]#{i} Evidence:[/bold]")
            for e in s.evidence:
                out.print(f"  - {e}")

    if verbose and result.reasoning_log:
        out.print()
        out.print(Panel(result.reasoning_log, title="Reasoning Log", border_style="dim"))


def _report_fault_markdown(result) -> str:
    lines = ["# Fault Localization Report\n"]
    if not result.suspects:
        lines.append("No suspect locations identified.\n")
    else:
        lines.append("## Suspect Locations\n")
        lines.append("| # | Score | File | Lines | Hypothesis |")
        lines.append("|---|-------|------|-------|------------|")
        for i, s in enumerate(result.suspects, 1):
            score_pct = f"{s.suspicion_score * 100:.0f}%"
            lines.append(f"| {i} | {score_pct} | `{s.file}` | {s.line_start}-{s.line_end} | {s.hypothesis} |")

        for i, s in enumerate(result.suspects, 1):
            if s.evidence:
                lines.append(f"\n### #{i} Evidence\n")
                for e in s.evidence:
                    lines.append(f"- {e}")

    if result.reasoning_log:
        lines.append("\n## Reasoning Log\n")
        lines.append(result.reasoning_log)

    return "\n".join(lines)


def _report_fault_json(result) -> str:
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


# --- F9: Patch equivalence command ---

@cli.command("patch-equiv")
@click.option("--sandbox-a", type=int, default=None, help="First Everest sandbox ID")
@click.option("--sandbox-b", type=int, default=None, help="Second Everest sandbox ID")
@click.option("--ref-a", default=None, help="First git revision range")
@click.option("--ref-b", default=None, help="Second git revision range")
@click.option("--file-a", type=click.Path(exists=True), default=None, help="First diff file")
@click.option("--file-b", type=click.Path(exists=True), default=None, help="Second diff file")
@click.option("--format", "output_format", type=click.Choice(["terminal", "markdown", "json"]), default="terminal")
@click.option("--verbose", "-v", is_flag=True, help="Show reasoning log")
@click.option("--repo", default=".", help="Path to git repository")
def patch_equiv(
    sandbox_a: int | None, sandbox_b: int | None,
    ref_a: str | None, ref_b: str | None,
    file_a: str | None, file_b: str | None,
    output_format: str, verbose: bool, repo: str,
) -> None:
    """Compare two patches for behavioral equivalence.

    Provide exactly one pair of inputs:

    \b
      --sandbox-a / --sandbox-b    Two Everest sandbox IDs
      --ref-a / --ref-b            Two git revision ranges
      --file-a / --file-b          Two diff files
    """
    from fb_review_agent.equivalence.compare import run_patch_equivalence

    config: Config = click.get_current_context().obj["config"]
    repo_root = repo
    if git.is_git_repo(repo):
        try:
            repo_root = git.get_repo_root(repo)
        except git.GitError:
            pass

    # Resolve patch texts
    patch_a_text: str | None = None
    patch_b_text: str | None = None

    if sandbox_a is not None and sandbox_b is not None:
        console.print(f"[bold]Comparing sandboxes {sandbox_a} vs {sandbox_b}[/bold]")
        try:
            patch_a_text = everest.get_evsts_sandbox_diff(sandbox_a)
            patch_b_text = everest.get_evsts_sandbox_diff(sandbox_b)
        except everest.EvCliError as e:
            console.print(f"[red]evsts error:[/red] {e}")
            sys.exit(1)
    elif ref_a is not None and ref_b is not None:
        console.print(f"[bold]Comparing refs {ref_a} vs {ref_b}[/bold]")
        try:
            patch_a_text = git.get_diff(ref_a, cwd=repo_root)
            patch_b_text = git.get_diff(ref_b, cwd=repo_root)
        except git.GitError as e:
            console.print(f"[red]Git error:[/red] {e}")
            sys.exit(1)
    elif file_a is not None and file_b is not None:
        console.print(f"[bold]Comparing diff files {file_a} vs {file_b}[/bold]")
        patch_a_text = Path(file_a).read_text()
        patch_b_text = Path(file_b).read_text()
    else:
        console.print("[red]Error:[/red] Provide exactly one pair: --sandbox-a/--sandbox-b, --ref-a/--ref-b, or --file-a/--file-b")
        sys.exit(1)

    if not patch_a_text or not patch_a_text.strip():
        console.print("[yellow]Patch A is empty.[/yellow]")
        sys.exit(1)
    if not patch_b_text or not patch_b_text.strip():
        console.print("[yellow]Patch B is empty.[/yellow]")
        sys.exit(1)

    console.print(f"[dim]Model: {config.model} | Max turns: {config.max_turns}[/dim]\n")

    result = run_patch_equivalence(
        patch_a=patch_a_text,
        patch_b=patch_b_text,
        config=config,
        repo_root=repo_root,
        on_tool_call=_tool_call_callback,
    )

    if output_format == "terminal":
        _report_equiv_terminal(result, verbose)
    elif output_format == "markdown":
        click.echo(_report_equiv_markdown(result))
    elif output_format == "json":
        click.echo(_report_equiv_json(result))


def _report_equiv_terminal(result, verbose: bool) -> None:
    from rich.panel import Panel
    from rich.table import Table

    out = Console()

    verdict_styles = {
        "equivalent": ("green", "EQUIVALENT"),
        "not_equivalent": ("red", "NOT EQUIVALENT"),
        "uncertain": ("yellow", "UNCERTAIN"),
    }
    style, label = verdict_styles.get(result.verdict.value, ("white", result.verdict.value.upper()))
    out.print(Panel(
        f"[{style} bold]{label}[/{style} bold]  (confidence: {result.confidence})",
        title="Equivalence Verdict",
        border_style=style,
    ))

    if result.differences:
        out.print()
        table = Table(title="Behavioral Differences", show_lines=True)
        table.add_column("#", width=3)
        table.add_column("Severity", width=10)
        table.add_column("Description", min_width=30)
        table.add_column("Diverging Input", min_width=20)

        for i, d in enumerate(result.differences, 1):
            sev_style = {"breaking": "red", "minor": "yellow", "cosmetic": "blue"}.get(d.severity, "white")
            table.add_row(
                str(i),
                f"[{sev_style}]{d.severity}[/{sev_style}]",
                d.description,
                d.input_that_differs,
            )

        out.print(table)

        for i, d in enumerate(result.differences, 1):
            out.print(f"\n[bold]#{i}:[/bold] {d.description}")
            out.print(f"  Patch A: {d.patch_a_behavior}")
            out.print(f"  Patch B: {d.patch_b_behavior}")

    if verbose and result.reasoning_log:
        out.print()
        out.print(Panel(result.reasoning_log, title="Reasoning Log", border_style="dim"))


def _report_equiv_markdown(result) -> str:
    lines = ["# Patch Equivalence Report\n"]
    lines.append(f"**Verdict:** {result.verdict.value} | **Confidence:** {result.confidence}\n")

    if result.differences:
        lines.append("## Behavioral Differences\n")
        lines.append("| # | Severity | Description | Diverging Input |")
        lines.append("|---|----------|-------------|-----------------|")
        for i, d in enumerate(result.differences, 1):
            lines.append(f"| {i} | {d.severity} | {d.description} | {d.input_that_differs} |")

        for i, d in enumerate(result.differences, 1):
            lines.append(f"\n### Difference #{i}: {d.description}\n")
            lines.append(f"- **Patch A:** {d.patch_a_behavior}")
            lines.append(f"- **Patch B:** {d.patch_b_behavior}")
    else:
        lines.append("No behavioral differences found.\n")

    if result.reasoning_log:
        lines.append("\n## Reasoning Log\n")
        lines.append(result.reasoning_log)

    return "\n".join(lines)


def _report_equiv_json(result) -> str:
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
