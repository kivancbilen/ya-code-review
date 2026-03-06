"""F8: Fault localization — agent-driven bug localization using semi-formal reasoning."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from fb_review_agent.agent.loop import run_agent_loop
from fb_review_agent.config import Config
from fb_review_agent.reasoning.fault_localization import FaultLocalizationTemplate


@dataclass
class SuspectLocation:
    """A suspected fault location with evidence."""

    file: str
    line_start: int
    line_end: int
    suspicion_score: float  # 0.0-1.0
    hypothesis: str
    evidence: list[str] = field(default_factory=list)


@dataclass
class FaultLocalizationResult:
    """Result of fault localization analysis."""

    suspects: list[SuspectLocation] = field(default_factory=list)
    reasoning_log: str = ""
    raw_response: str = ""


def _parse_fault_response(response: str) -> FaultLocalizationResult:
    """Extract suspect locations from the agent's response."""
    # Try JSON code block
    json_match = re.search(r"```json\s*\n(.*?)\n\s*```", response, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group(1))
            return _build_result(data, response)
        except json.JSONDecodeError:
            pass

    # Try raw JSON
    brace_matches = list(re.finditer(r"\{", response))
    for match in reversed(brace_matches):
        try:
            data = json.loads(response[match.start():])
            if "suspects" in data:
                return _build_result(data, response)
        except (json.JSONDecodeError, ValueError):
            continue

    return FaultLocalizationResult(reasoning_log=response, raw_response=response)


def _build_result(data: dict, raw_response: str) -> FaultLocalizationResult:
    """Build FaultLocalizationResult from parsed JSON."""
    suspects = []
    for s in data.get("suspects", []):
        suspects.append(SuspectLocation(
            file=s.get("file", ""),
            line_start=s.get("line_start", 0),
            line_end=s.get("line_end", 0),
            suspicion_score=float(s.get("suspicion_score", 0.0)),
            hypothesis=s.get("hypothesis", ""),
            evidence=s.get("evidence", []),
        ))
    # Sort by suspicion score descending
    suspects.sort(key=lambda x: x.suspicion_score, reverse=True)
    return FaultLocalizationResult(
        suspects=suspects,
        reasoning_log=data.get("reasoning_log", ""),
        raw_response=raw_response,
    )


def run_fault_localization(
    bug_description: str,
    config: Config,
    repo_root: str,
    diff_ref: str | None = None,
    on_tool_call: Callable[[str, dict], None] | None = None,
) -> FaultLocalizationResult:
    """Run the fault localization agent.

    Uses the 5-phase fault localization template to systematically
    identify suspect code locations for a described bug.
    """
    template = FaultLocalizationTemplate()
    system_prompt = template.build_system_prompt()

    # Build user message with optional diff context
    diff_text = ""
    if diff_ref:
        from fb_review_agent.integrations.git import get_diff
        try:
            diff_text = get_diff(diff_ref, cwd=repo_root)
        except Exception:
            diff_text = ""

    user_message = template.build_user_message(
        bug_description=bug_description,
        diff=diff_text,
    )

    raw_response = run_agent_loop(
        system_prompt=system_prompt,
        user_message=user_message,
        config=config,
        repo_root=repo_root,
        on_tool_call=on_tool_call,
    )

    return _parse_fault_response(raw_response)
