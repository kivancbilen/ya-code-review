"""Output formatting: terminal (rich), markdown, JSON."""

from __future__ import annotations

import json

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from fb_review_agent.coverage.analyzer import CoverageReport
from fb_review_agent.review.finding import Finding, ReviewResult, Severity


SEVERITY_COLORS = {
    Severity.CRITICAL: "red bold",
    Severity.HIGH: "red",
    Severity.MEDIUM: "yellow",
    Severity.LOW: "blue",
}

SEVERITY_ICONS = {
    Severity.CRITICAL: "[!]",
    Severity.HIGH: "[H]",
    Severity.MEDIUM: "[M]",
    Severity.LOW: "[L]",
}


def _guess_lexer(file_path: str) -> str:
    """Guess syntax highlighting lexer from file extension."""
    ext = file_path.rsplit(".", 1)[-1] if "." in file_path else ""
    return {
        "ts": "typescript", "tsx": "tsx", "js": "javascript", "jsx": "jsx",
        "py": "python", "json": "json", "ls": "text", "md": "markdown",
        "yaml": "yaml", "yml": "yaml", "css": "css", "html": "html",
    }.get(ext, "text")


def _render_references_terminal(f: Finding, console: Console) -> None:
    """Render code references for a finding."""
    if not f.references:
        return
    for ref in f.references:
        header = f"[dim]{ref.file}:{ref.line_start}-{ref.line_end}[/dim]"
        if ref.label:
            header += f"  [italic]{ref.label}[/italic]"
        console.print(header)
        if ref.snippet.strip():
            lexer = _guess_lexer(ref.file)
            syntax = Syntax(
                ref.snippet.rstrip(),
                lexer,
                line_numbers=True,
                start_line=ref.line_start if ref.line_start > 0 else 1,
                theme="monokai",
                padding=(0, 1),
            )
            console.print(syntax)
        console.print()


def report_terminal(result: ReviewResult, console: Console | None = None, verbose: bool = False) -> None:
    """Print review results to the terminal using rich formatting."""
    console = console or Console()

    # Summary panel
    s = result.summary
    summary_text = (
        f"Files reviewed: {s.total_files_reviewed}  |  "
        f"Findings: {s.total_findings}  |  "
        f"Critical: {s.critical}  High: {s.high}  Medium: {s.medium}  Low: {s.low}\n"
        f"Premises: {s.premises_established}  |  Traces: {s.traces_performed}  |  "
        f"Claims: {s.claims_investigated}  |  Refuted: {s.claims_refuted}"
    )
    console.print(Panel(summary_text, title="Review Summary", border_style="bold"))
    console.print()

    if not result.findings:
        console.print("[green bold]No issues found.[/green bold] The changes look correct based on semi-formal analysis.")
        if verbose and result.reasoning_log:
            console.print()
            console.print(Panel(result.reasoning_log, title="Reasoning Log", border_style="dim"))
        return

    # Findings table
    table = Table(title="Findings", show_lines=True)
    table.add_column("ID", style="bold", width=4)
    table.add_column("Sev", width=6)
    table.add_column("Conf", width=6)
    table.add_column("Title", min_width=30)
    table.add_column("Location", min_width=20)
    table.add_column("Category", width=14)

    for f in result.findings:
        sev_style = SEVERITY_COLORS.get(f.severity, "")
        table.add_row(
            f.id,
            f"[{sev_style}]{SEVERITY_ICONS.get(f.severity, '')} {f.severity.value}[/{sev_style}]",
            f.confidence.value,
            f.title,
            f"{f.file}:{f.line_start}-{f.line_end}",
            f.category.value,
        )

    console.print(table)
    console.print()

    # Detailed findings with code references
    for f in result.findings:
        sev_style = SEVERITY_COLORS.get(f.severity, "")

        body = f"[bold]{f.title}[/bold]\n\n{f.description}\n"
        body += f"\n[dim]Evidence chain: {' → '.join(f.evidence_chain)}[/dim]"
        if f.suggestion:
            body += f"\n\n[green]Suggestion:[/green] {f.suggestion}"

        console.print(Panel(
            body,
            title=f"[{sev_style}]{f.id}: {f.severity.value.upper()}[/{sev_style}] — {f.file}:{f.line_start}",
            border_style=sev_style.split()[0] if sev_style else "white",
        ))

        # Code references below the panel
        _render_references_terminal(f, console)

    if verbose and result.reasoning_log:
        console.print()
        console.print(Panel(result.reasoning_log, title="Reasoning Log", border_style="dim"))


def report_markdown(result: ReviewResult) -> str:
    """Generate a markdown report of the review results."""
    lines = ["# Code Review — Semi-Formal Reasoning Analysis\n"]

    s = result.summary
    lines.append("## Summary\n")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Files reviewed | {s.total_files_reviewed} |")
    lines.append(f"| Total findings | {s.total_findings} |")
    lines.append(f"| Critical | {s.critical} |")
    lines.append(f"| High | {s.high} |")
    lines.append(f"| Medium | {s.medium} |")
    lines.append(f"| Low | {s.low} |")
    lines.append(f"| Premises established | {s.premises_established} |")
    lines.append(f"| Execution traces | {s.traces_performed} |")
    lines.append(f"| Claims investigated | {s.claims_investigated} |")
    lines.append(f"| Claims refuted | {s.claims_refuted} |")
    lines.append("")

    if not result.findings:
        lines.append("**No issues found.** The changes look correct based on semi-formal analysis.\n")
    else:
        lines.append("## Findings\n")
        for f in result.findings:
            icon = {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🔵"}.get(f.severity.value, "⚪")
            lines.append(f"### {icon} {f.id}: {f.title}\n")
            lines.append(f"- **Severity:** {f.severity.value} | **Confidence:** {f.confidence.value} | **Category:** {f.category.value}")
            lines.append(f"- **Location:** `{f.file}:{f.line_start}-{f.line_end}`")
            lines.append(f"- **Evidence chain:** {' → '.join(f.evidence_chain)}\n")
            lines.append(f"{f.description}\n")

            # Code references
            if f.references:
                lines.append("**References:**\n")
                for ref in f.references:
                    label = f" — {ref.label}" if ref.label else ""
                    lines.append(f"`{ref.file}:{ref.line_start}-{ref.line_end}`{label}\n")
                    if ref.snippet.strip():
                        lexer = _guess_lexer(ref.file)
                        lines.append(f"```{lexer}")
                        lines.append(ref.snippet.rstrip())
                        lines.append("```\n")

            if f.suggestion:
                lines.append(f"> **Suggestion:** {f.suggestion}\n")

    if result.reasoning_log:
        lines.append("## Reasoning Log\n")
        lines.append(result.reasoning_log)

    return "\n".join(lines)


def report_coverage_terminal(report: CoverageReport, console: Console | None = None) -> None:
    """Print coverage analysis to the terminal using rich formatting."""
    console = console or Console()

    ratio_pct = f"{report.coverage_ratio * 100:.0f}%"
    summary = f"Coverage ratio: {ratio_pct}  |  Symbols analyzed: {len(report.mappings)}  |  Uncovered: {len(report.uncovered_symbols)}"
    console.print(Panel(summary, title="Test Coverage Analysis", border_style="bold"))
    console.print()

    if not report.mappings:
        console.print("[dim]No changed symbols detected in diff hunks.[/dim]")
        return

    table = Table(title="Changed Symbols — Test Coverage", show_lines=True)
    table.add_column("Symbol", min_width=20)
    table.add_column("File", min_width=20)
    table.add_column("Lines", width=10)
    table.add_column("Coverage", width=10)
    table.add_column("Test Files", min_width=30)

    conf_styles = {"high": "green", "medium": "yellow", "low": "blue", "none": "red"}

    for m in report.mappings:
        style = conf_styles.get(m.confidence, "white")
        test_str = ", ".join(m.test_files[:3]) if m.test_files else "(none)"
        if len(m.test_files) > 3:
            test_str += f" +{len(m.test_files) - 3} more"
        table.add_row(
            m.symbol.name,
            m.symbol.file,
            f"{m.symbol.line_start}-{m.symbol.line_end}",
            f"[{style}]{m.confidence}[/{style}]",
            test_str,
        )

    console.print(table)

    if report.uncovered_symbols:
        console.print()
        console.print("[red bold]Uncovered symbols:[/red bold]")
        for sym in report.uncovered_symbols:
            console.print(f"  [red]- {sym.name}[/red] ({sym.file}:{sym.line_start})")


def report_coverage_markdown(report: CoverageReport) -> str:
    """Generate a markdown coverage report."""
    lines = ["## Test Coverage Analysis\n"]
    ratio_pct = f"{report.coverage_ratio * 100:.0f}%"
    lines.append(f"**Coverage ratio:** {ratio_pct} | **Symbols analyzed:** {len(report.mappings)} | **Uncovered:** {len(report.uncovered_symbols)}\n")

    if not report.mappings:
        lines.append("No changed symbols detected in diff hunks.\n")
        return "\n".join(lines)

    lines.append("| Symbol | File | Lines | Coverage | Test Files |")
    lines.append("|--------|------|-------|----------|------------|")
    for m in report.mappings:
        test_str = ", ".join(f"`{t}`" for t in m.test_files[:3]) if m.test_files else "(none)"
        lines.append(f"| {m.symbol.name} | {m.symbol.file} | {m.symbol.line_start}-{m.symbol.line_end} | {m.confidence} | {test_str} |")

    if report.uncovered_symbols:
        lines.append("\n### Uncovered Symbols\n")
        for sym in report.uncovered_symbols:
            lines.append(f"- **{sym.name}** (`{sym.file}:{sym.line_start}`)")

    lines.append("")
    return "\n".join(lines)


def report_json(result: ReviewResult) -> str:
    """Generate a JSON report of the review results."""
    data = {
        "findings": [
            {
                "id": f.id,
                "severity": f.severity.value,
                "confidence": f.confidence.value,
                "title": f.title,
                "file": f.file,
                "line_start": f.line_start,
                "line_end": f.line_end,
                "description": f.description,
                "evidence_chain": f.evidence_chain,
                "references": [
                    {
                        "file": ref.file,
                        "line_start": ref.line_start,
                        "line_end": ref.line_end,
                        "snippet": ref.snippet,
                        "label": ref.label,
                    }
                    for ref in f.references
                ],
                "suggestion": f.suggestion,
                "category": f.category.value,
            }
            for f in result.findings
        ],
        "summary": {
            "total_files_reviewed": result.summary.total_files_reviewed,
            "total_findings": result.summary.total_findings,
            "critical": result.summary.critical,
            "high": result.summary.high,
            "medium": result.summary.medium,
            "low": result.summary.low,
            "premises_established": result.summary.premises_established,
            "traces_performed": result.summary.traces_performed,
            "claims_investigated": result.summary.claims_investigated,
            "claims_refuted": result.summary.claims_refuted,
        },
        "reasoning_log": result.reasoning_log,
    }
    return json.dumps(data, indent=2)
