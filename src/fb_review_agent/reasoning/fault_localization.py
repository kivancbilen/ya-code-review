"""F8: Fault localization reasoning template — 5-phase semi-formal methodology."""

from __future__ import annotations

import json
import re

from fb_review_agent.reasoning.code_review import _load_template


class FaultLocalizationTemplate:
    """Semi-formal fault localization template implementing 5-phase methodology."""

    @property
    def name(self) -> str:
        return "fault_localization"

    def build_system_prompt(self) -> str:
        return _load_template("system_prompt.md")

    def build_user_message(self, *, bug_description: str, diff: str = "", **kwargs: str) -> str:
        template = _load_template("fault_localization.md")
        return template.format(bug_description=bug_description, diff=diff or "(no diff provided)")

    def parse_response(self, response: str) -> dict:
        """Extract the JSON suspects block from the agent's response."""
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
                if "suspects" in data:
                    return data
            except (json.JSONDecodeError, ValueError):
                continue

        return {
            "suspects": [],
            "reasoning_log": response,
        }
