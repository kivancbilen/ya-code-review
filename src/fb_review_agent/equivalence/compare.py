"""F9: Patch equivalence — compare two patches for behavioral equivalence."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

from fb_review_agent.agent.loop import run_agent_loop
from fb_review_agent.config import Config
from fb_review_agent.reasoning.patch_equivalence import PatchEquivalenceTemplate


class EquivalenceVerdict(str, Enum):
    EQUIVALENT = "equivalent"
    NOT_EQUIVALENT = "not_equivalent"
    UNCERTAIN = "uncertain"


@dataclass
class BehavioralDifference:
    """A specific behavioral difference between two patches."""

    description: str
    input_that_differs: str
    patch_a_behavior: str
    patch_b_behavior: str
    severity: str = "minor"  # breaking/minor/cosmetic


@dataclass
class EquivalenceResult:
    """Result of patch equivalence analysis."""

    verdict: EquivalenceVerdict = EquivalenceVerdict.UNCERTAIN
    confidence: str = "low"
    differences: list[BehavioralDifference] = field(default_factory=list)
    reasoning_log: str = ""
    raw_response: str = ""


def _parse_equivalence_response(response: str) -> EquivalenceResult:
    """Extract equivalence verdict from the agent's response."""
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
            if "verdict" in data:
                return _build_result(data, response)
        except (json.JSONDecodeError, ValueError):
            continue

    return EquivalenceResult(reasoning_log=response, raw_response=response)


def _build_result(data: dict, raw_response: str) -> EquivalenceResult:
    """Build EquivalenceResult from parsed JSON."""
    differences = []
    for d in data.get("differences", []):
        differences.append(BehavioralDifference(
            description=d.get("description", ""),
            input_that_differs=d.get("input_that_differs", ""),
            patch_a_behavior=d.get("patch_a_behavior", ""),
            patch_b_behavior=d.get("patch_b_behavior", ""),
            severity=d.get("severity", "minor"),
        ))

    try:
        verdict = EquivalenceVerdict(data.get("verdict", "uncertain"))
    except ValueError:
        verdict = EquivalenceVerdict.UNCERTAIN

    return EquivalenceResult(
        verdict=verdict,
        confidence=data.get("confidence", "low"),
        differences=differences,
        reasoning_log=data.get("reasoning_log", ""),
        raw_response=raw_response,
    )


def run_patch_equivalence(
    patch_a: str,
    patch_b: str,
    config: Config,
    repo_root: str,
    on_tool_call: Callable[[str, dict], None] | None = None,
) -> EquivalenceResult:
    """Run the patch equivalence agent.

    Uses the 5-phase patch equivalence template to systematically
    compare two patches for behavioral equivalence.
    """
    template = PatchEquivalenceTemplate()
    system_prompt = template.build_system_prompt()
    user_message = template.build_user_message(
        patch_a=patch_a,
        patch_b=patch_b,
    )

    raw_response = run_agent_loop(
        system_prompt=system_prompt,
        user_message=user_message,
        config=config,
        repo_root=repo_root,
        on_tool_call=on_tool_call,
    )

    return _parse_equivalence_response(raw_response)
