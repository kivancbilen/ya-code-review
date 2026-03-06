"""F9: Patch equivalence reasoning template — 5-phase semi-formal methodology."""

from __future__ import annotations

import json
import re

from fb_review_agent.reasoning.code_review import _load_template


class PatchEquivalenceTemplate:
    """Semi-formal patch equivalence template implementing 5-phase methodology."""

    @property
    def name(self) -> str:
        return "patch_equivalence"

    def build_system_prompt(self) -> str:
        return _load_template("system_prompt.md")

    def build_user_message(self, *, patch_a: str, patch_b: str, **kwargs: str) -> str:
        template = _load_template("patch_equivalence.md")
        return template.format(patch_a=patch_a, patch_b=patch_b)

    def parse_response(self, response: str) -> dict:
        """Extract the JSON verdict block from the agent's response."""
        json_match = re.search(r"```json\s*\n(.*?)\n\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        brace_matches = list(re.finditer(r"\{", response))
        for match in reversed(brace_matches):
            try:
                data = json.loads(response[match.start():])
                if "verdict" in data:
                    return data
            except (json.JSONDecodeError, ValueError):
                continue

        return {
            "verdict": "uncertain",
            "confidence": "low",
            "differences": [],
            "reasoning_log": response,
        }
