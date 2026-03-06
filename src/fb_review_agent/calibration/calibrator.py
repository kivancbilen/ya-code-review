"""F4: Auto-severity calibration — LLM post-processing to recalibrate finding severities."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import anthropic

from fb_review_agent.config import Config
from fb_review_agent.review.finding import Finding, Severity


@dataclass
class CalibrationResult:
    """Result of severity calibration pass."""

    original_findings: list[Finding]
    calibrated_findings: list[Finding]
    adjustments: list[dict] = field(default_factory=list)  # {finding_id, old_severity, new_severity, reason}


CALIBRATION_SYSTEM_PROMPT = """\
You are a severity calibration expert for code review findings. Your job is to evaluate \
each finding and recalibrate its severity based on context.

For each finding, evaluate:
1. **Impact scope** — How many callers/consumers are affected?
2. **Hot path** — Is this in a critical execution path?
3. **Defensive code** — Are there existing guards/checks that mitigate this?
4. **Test coverage indicators** — Does the evidence mention tests covering this?
5. **Reversibility** — How hard would this be to fix in production?

Output a JSON array of adjustments. Only include findings where the severity should change.

```json
{
  "adjustments": [
    {
      "finding_id": "F1",
      "old_severity": "high",
      "new_severity": "medium",
      "reason": "Brief explanation for the change"
    }
  ]
}
```

If no adjustments are needed, return: `{"adjustments": []}`
"""


def _build_calibration_message(findings: list[Finding], diff_text: str) -> str:
    """Build the user message for the calibration LLM call."""
    lines = ["## Findings to Calibrate\n"]
    for f in findings:
        lines.append(f"### {f.id}: {f.title}")
        lines.append(f"- Severity: {f.severity.value}")
        lines.append(f"- Confidence: {f.confidence.value}")
        lines.append(f"- File: {f.file}:{f.line_start}-{f.line_end}")
        lines.append(f"- Category: {f.category.value}")
        lines.append(f"- Description: {f.description}")
        if f.evidence_chain:
            lines.append(f"- Evidence: {', '.join(f.evidence_chain)}")
        if f.suggestion:
            lines.append(f"- Suggestion: {f.suggestion}")
        lines.append("")

    lines.append("## Diff Context\n")
    # Limit diff to avoid token overflow
    if len(diff_text) > 50_000:
        lines.append(diff_text[:50_000])
        lines.append("\n... (diff truncated)")
    else:
        lines.append(diff_text)

    return "\n".join(lines)


def _parse_calibration_response(response_text: str) -> list[dict]:
    """Extract adjustments from the calibration LLM response."""
    # Try JSON code block first
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", response_text, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return data.get("adjustments", [])
        except json.JSONDecodeError:
            pass

    # Try raw JSON
    brace_matches = list(re.finditer(r"\{", response_text))
    for match in reversed(brace_matches):
        try:
            data = json.loads(response_text[match.start():])
            if "adjustments" in data:
                return data["adjustments"]
        except (json.JSONDecodeError, ValueError):
            continue

    return []


def calibrate_findings(
    findings: list[Finding],
    diff_text: str,
    config: Config,
    repo_root: str,
) -> CalibrationResult:
    """Run a single LLM call to recalibrate finding severities.

    Uses a fast/cheap model (default: claude-haiku-4-5-20251001) for speed.
    """
    if not findings:
        return CalibrationResult(
            original_findings=[],
            calibrated_findings=[],
            adjustments=[],
        )

    # Deep copy findings for calibration
    calibrated = []
    for f in findings:
        calibrated.append(Finding(
            id=f.id,
            severity=f.severity,
            confidence=f.confidence,
            title=f.title,
            file=f.file,
            line_start=f.line_start,
            line_end=f.line_end,
            description=f.description,
            evidence_chain=list(f.evidence_chain),
            references=list(f.references),
            suggestion=f.suggestion,
            category=f.category,
        ))

    client = anthropic.Anthropic(api_key=config.get_api_key())
    user_message = _build_calibration_message(findings, diff_text)

    response = client.messages.create(
        model=config.calibration_model,
        max_tokens=4096,
        system=CALIBRATION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_message}],
    )

    response_text = ""
    for block in response.content:
        if block.type == "text":
            response_text += block.text

    adjustments = _parse_calibration_response(response_text)

    # Apply adjustments
    finding_map = {f.id: f for f in calibrated}
    for adj in adjustments:
        fid = adj.get("finding_id", "")
        new_sev = adj.get("new_severity", "")
        if fid in finding_map and new_sev:
            try:
                finding_map[fid].severity = Severity(new_sev)
            except ValueError:
                pass  # Invalid severity value, skip

    return CalibrationResult(
        original_findings=findings,
        calibrated_findings=calibrated,
        adjustments=adjustments,
    )
