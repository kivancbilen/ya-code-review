"""Orchestrator: multi-pass ensemble review at different chunk granularities."""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Callable

from rich.console import Console

from fb_review_agent.agent.loop import run_agent_loop
from fb_review_agent.calibration.calibrator import calibrate_findings
from fb_review_agent.config import Config
from fb_review_agent.memory.store import PatternStore, format_patterns_for_template
from fb_review_agent.reasoning.code_review import CodeReviewTemplate
from fb_review_agent.review.diff_parser import FileDiff, ParsedDiff, parse_diff
from fb_review_agent.review.finding import (
    Finding,
    ReviewResult,
    ReviewSummary,
)


console = Console(stderr=True)

# Three pass sizes: fine, medium, coarse
PASS_CONFIGS = [
    {"name": "fine",   "chunk_chars": 20_000,  "label": "Deep line-level analysis"},
    {"name": "medium", "chunk_chars": 50_000,  "label": "Cross-file pattern detection"},
    {"name": "coarse", "chunk_chars": 200_000, "label": "Architectural overview"},
]


def _reconstruct_file_diff(f: FileDiff) -> str:
    """Reconstruct a unified diff string for a single FileDiff."""
    lines = []
    lines.append(f"diff --git a/{f.source_file} b/{f.target_file}")
    if f.is_new:
        lines.append("new file mode 100644")
        lines.append("--- /dev/null")
        lines.append(f"+++ b/{f.target_file}")
    elif f.is_deleted:
        lines.append("deleted file mode 100644")
        lines.append(f"--- a/{f.source_file}")
        lines.append("+++ /dev/null")
    else:
        lines.append(f"--- a/{f.source_file}")
        lines.append(f"+++ b/{f.target_file}")

    for hunk in f.hunks:
        lines.append(f"@@ -{hunk.source_start},{hunk.source_length} +{hunk.target_start},{hunk.target_length} @@")
        lines.append(hunk.content.rstrip("\n"))

    return "\n".join(lines) + "\n"


def _chunk_files(files: list[FileDiff], max_chars: int) -> list[list[FileDiff]]:
    """Split files into chunks where each chunk's reconstructed diff fits under max_chars."""
    chunks: list[list[FileDiff]] = []
    current_chunk: list[FileDiff] = []
    current_size = 0

    for f in files:
        file_diff_text = _reconstruct_file_diff(f)
        file_size = len(file_diff_text)

        if file_size > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_size = 0
            chunks.append([f])
            continue

        if current_size + file_size > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            current_size = 0

        current_chunk.append(f)
        current_size += file_size

    if current_chunk:
        chunks.append(current_chunk)

    return chunks


# --- Deduplication ---

def _findings_similar(a: Finding, b: Finding) -> bool:
    """Check if two findings are about the same issue (should be deduplicated)."""
    # Same file and overlapping line ranges → likely same issue
    if a.file == b.file:
        overlap = (
            a.line_start <= b.line_end and b.line_start <= a.line_end
        ) if a.line_start > 0 and b.line_start > 0 else False
        if overlap:
            title_sim = SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio()
            if title_sim > 0.4:
                return True

    # Different files but very similar titles → likely same pattern finding
    title_sim = SequenceMatcher(None, a.title.lower(), b.title.lower()).ratio()
    desc_sim = SequenceMatcher(
        None,
        a.description[:200].lower(),
        b.description[:200].lower(),
    ).ratio()

    if title_sim > 0.7 and desc_sim > 0.5:
        return True

    return False


def _pick_best(a: Finding, b: Finding) -> Finding:
    """Pick the better of two duplicate findings."""
    severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    confidence_order = {"high": 0, "medium": 1, "low": 2}

    a_score = (
        severity_order.get(a.severity.value, 9),
        confidence_order.get(a.confidence.value, 9),
        -len(a.references),
        -len(a.description),
    )
    b_score = (
        severity_order.get(b.severity.value, 9),
        confidence_order.get(b.confidence.value, 9),
        -len(b.references),
        -len(b.description),
    )

    winner = a if a_score <= b_score else b
    loser = b if winner is a else a

    # Merge references from the loser into the winner
    existing_snippets = {r.snippet.strip() for r in winner.references if r.snippet}
    for ref in loser.references:
        if ref.snippet.strip() not in existing_snippets:
            winner.references.append(ref)
            existing_snippets.add(ref.snippet.strip())

    return winner


def _deduplicate_findings(findings: list[Finding]) -> list[Finding]:
    """Remove duplicate findings, keeping the best version of each."""
    if not findings:
        return []

    deduped: list[Finding] = []
    for f in findings:
        merged = False
        for i, existing in enumerate(deduped):
            if _findings_similar(f, existing):
                deduped[i] = _pick_best(existing, f)
                merged = True
                break
        if not merged:
            deduped.append(f)

    # Re-number
    for i, f in enumerate(deduped):
        f.id = f"F{i + 1}"

    return deduped


# --- Merge ---

def _merge_results(results: list[ReviewResult], pass_labels: list[str] | None = None) -> ReviewResult:
    """Merge multiple review results, deduplicating findings."""
    all_findings: list[Finding] = []
    all_reasoning: list[str] = []
    total_summary = ReviewSummary()

    for i, r in enumerate(results):
        label = pass_labels[i] if pass_labels and i < len(pass_labels) else f"Pass {i + 1}"
        all_findings.extend(r.findings)

        if r.reasoning_log:
            all_reasoning.append(f"--- {label} ---\n{r.reasoning_log}")

        s = r.summary
        total_summary.total_files_reviewed = max(total_summary.total_files_reviewed, s.total_files_reviewed)
        total_summary.premises_established += s.premises_established
        total_summary.traces_performed += s.traces_performed
        total_summary.claims_investigated += s.claims_investigated
        total_summary.claims_refuted += s.claims_refuted

    # Deduplicate across all passes
    deduped = _deduplicate_findings(all_findings)

    total_summary.total_findings = len(deduped)
    total_summary.critical = sum(1 for f in deduped if f.severity.value == "critical")
    total_summary.high = sum(1 for f in deduped if f.severity.value == "high")
    total_summary.medium = sum(1 for f in deduped if f.severity.value == "medium")
    total_summary.low = sum(1 for f in deduped if f.severity.value == "low")

    return ReviewResult(
        findings=deduped,
        summary=total_summary,
        reasoning_log="\n\n".join(all_reasoning),
        raw_response="",
    )


# --- Single-pass review ---

def _maybe_calibrate(result: ReviewResult, diff_text: str, config: Config, repo_root: str) -> ReviewResult:
    """Run auto-severity calibration if enabled and there are findings."""
    if not config.calibration_enabled or not result.findings:
        return result

    try:
        console.print("[dim]Running auto-severity calibration...[/dim]")
        cal_result = calibrate_findings(result.findings, diff_text, config, repo_root)
        if cal_result.adjustments:
            adj_count = len(cal_result.adjustments)
            console.print(f"[dim]Calibration adjusted {adj_count} finding(s)[/dim]")
            for adj in cal_result.adjustments:
                console.print(f"  [dim]{adj.get('finding_id')}: {adj.get('old_severity')} → {adj.get('new_severity')} ({adj.get('reason', '')})[/dim]")
            result.findings = cal_result.calibrated_findings
            # Recount severities
            result.summary.critical = sum(1 for f in result.findings if f.severity.value == "critical")
            result.summary.high = sum(1 for f in result.findings if f.severity.value == "high")
            result.summary.medium = sum(1 for f in result.findings if f.severity.value == "medium")
            result.summary.low = sum(1 for f in result.findings if f.severity.value == "low")
        else:
            console.print("[dim]Calibration: no adjustments needed[/dim]")
    except Exception as e:
        console.print(f"[dim]Calibration skipped: {e}[/dim]")

    return result


def _run_single_pass(
    files: list[FileDiff],
    diff_text: str,
    chunk_chars: int,
    pass_name: str,
    pass_label: str,
    template: CodeReviewTemplate,
    system_prompt: str,
    config: Config,
    repo_root: str,
    on_tool_call: Callable[[str, dict], None] | None = None,
    known_patterns: str = "",
) -> ReviewResult:
    """Run a single review pass at a given chunk size."""
    chunks = _chunk_files(files, chunk_chars)

    if len(chunks) == 1:
        console.print(f"  [dim]1 chunk (full diff)[/dim]")
        return _review_chunk(chunks[0], diff_text, template, system_prompt, config, repo_root, on_tool_call, known_patterns=known_patterns)

    console.print(f"  [dim]{len(chunks)} chunks[/dim]")
    results = []
    for i, chunk in enumerate(chunks):
        chunk_files = [f.path for f in chunk]
        console.print(f"    [dim]Chunk {i + 1}/{len(chunks)}: {', '.join(chunk_files[:3])}{'...' if len(chunk_files) > 3 else ''}[/dim]")

        chunk_diff = "\n".join(_reconstruct_file_diff(f) for f in chunk)
        result = _review_chunk(chunk, chunk_diff, template, system_prompt, config, repo_root, on_tool_call, known_patterns=known_patterns)
        results.append(result)

        console.print(f"    [dim]→ {len(result.findings)} findings[/dim]")

    return _merge_results(results, pass_labels=[f"{pass_name} chunk {i+1}" for i in range(len(chunks))])


# --- Main entry point ---

def review_diff(
    diff_text: str,
    config: Config,
    repo_root: str,
    on_tool_call: Callable[[str, dict], None] | None = None,
) -> ReviewResult:
    """Run a multi-pass ensemble review at 3 chunk granularities.

    Pass 1 (fine):   small chunks → deep line-level bugs
    Pass 2 (medium): medium chunks → cross-file patterns
    Pass 3 (coarse): large chunks → architectural issues

    Findings are deduplicated across passes, keeping the best version.
    """
    parsed = parse_diff(diff_text)
    if not parsed.files:
        return ReviewResult(reasoning_log="No changes found in diff.")

    console.print(f"[dim]Reviewing {len(parsed.files)} changed files...[/dim]")
    console.print(f"[dim]{parsed.summary()}[/dim]\n")

    # F3: Load known patterns relevant to changed files
    known_patterns_text = ""
    try:
        store = PatternStore(config.get_memory_path())
        relevant_patterns = store.find_relevant(parsed.changed_files)
        if relevant_patterns:
            console.print(f"[dim]Found {len(relevant_patterns)} known patterns for changed files[/dim]")
            known_patterns_text = format_patterns_for_template(relevant_patterns)
            # Record hits
            for p in relevant_patterns:
                store.record_hit(p.id)
    except Exception:
        pass  # Memory is optional; don't fail the review

    template = CodeReviewTemplate()
    system_prompt = template.build_system_prompt()

    total_diff_size = len(diff_text)

    # Determine which passes are useful (skip if chunk size >= total diff)
    passes_to_run = []
    seen_chunk_counts = set()
    for pc in PASS_CONFIGS:
        chunks = _chunk_files(parsed.files, pc["chunk_chars"])
        chunk_count = len(chunks)
        if chunk_count not in seen_chunk_counts:
            passes_to_run.append(pc)
            seen_chunk_counts.add(chunk_count)

    if len(passes_to_run) == 1:
        # Small diff — single pass is enough
        console.print("[bold blue]Starting semi-formal reasoning review...[/bold blue]\n")
        result = _run_single_pass(
            parsed.files, diff_text, passes_to_run[0]["chunk_chars"],
            passes_to_run[0]["name"], passes_to_run[0]["label"],
            template, system_prompt, config, repo_root, on_tool_call,
            known_patterns=known_patterns_text,
        )
        return _maybe_calibrate(result, diff_text, config, repo_root)

    console.print(f"[bold blue]Multi-pass ensemble review — {len(passes_to_run)} passes at different granularities[/bold blue]\n")

    pass_results = []
    pass_labels = []
    for pc in passes_to_run:
        console.print(f"[bold]Pass: {pc['label']}[/bold] (chunk size: {pc['chunk_chars'] // 1000}K chars)")
        result = _run_single_pass(
            parsed.files, diff_text, pc["chunk_chars"],
            pc["name"], pc["label"],
            template, system_prompt, config, repo_root, on_tool_call,
            known_patterns=known_patterns_text,
        )
        pass_results.append(result)
        pass_labels.append(pc["label"])

        finding_count = len(result.findings)
        console.print(f"  [dim]→ {finding_count} findings from {pc['name']} pass[/dim]\n")

    # Merge and deduplicate across all passes
    total_before = sum(len(r.findings) for r in pass_results)
    merged = _merge_results(pass_results, pass_labels)
    total_after = len(merged.findings)

    if total_before > total_after:
        console.print(f"[dim]Deduplication: {total_before} raw findings → {total_after} unique findings[/dim]\n")

    return _maybe_calibrate(merged, diff_text, config, repo_root)


def _review_chunk(
    files: list[FileDiff],
    diff_text: str,
    template: CodeReviewTemplate,
    system_prompt: str,
    config: Config,
    repo_root: str,
    on_tool_call: Callable[[str, dict], None] | None = None,
    known_patterns: str = "",
) -> ReviewResult:
    """Review a single chunk of files."""
    user_message = template.build_user_message(diff=diff_text, known_patterns=known_patterns)

    raw_response = run_agent_loop(
        system_prompt=system_prompt,
        user_message=user_message,
        config=config,
        repo_root=repo_root,
        on_tool_call=on_tool_call,
    )

    parsed_result = template.parse_response(raw_response)
    return ReviewResult.from_parsed(parsed_result, raw_response=raw_response)
