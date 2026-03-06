"""Code review reasoning template — 5-phase semi-formal methodology."""

from __future__ import annotations

import json
import re
from importlib import resources


def _load_template(name: str) -> str:
    """Load a template file from the templates directory."""
    # Try package-relative path first, then fall back to file-relative path
    from pathlib import Path

    # Walk up from this file to find the templates directory
    pkg_root = Path(__file__).parent.parent.parent.parent  # fb-review-agent/
    template_path = pkg_root / "templates" / name
    if template_path.exists():
        return template_path.read_text()
    raise FileNotFoundError(f"Template not found: {name} (looked in {template_path})")


class CodeReviewTemplate:
    """Semi-formal code review template implementing the 5-phase methodology."""

    @property
    def name(self) -> str:
        return "code_review"

    def build_system_prompt(self) -> str:
        return _load_template("system_prompt.md")

    def build_user_message(self, *, diff: str, known_patterns: str = "", **kwargs: str) -> str:
        template = _load_template("code_review.md")
        return template.format(diff=diff, known_patterns=known_patterns, **kwargs)

    def parse_response(self, response: str) -> dict:
        """Extract the JSON findings block from the agent's response.

        The agent is instructed to end its response with a JSON block
        containing findings and summary.
        """
        # Try to find a JSON block in the response
        json_match = re.search(r"```json\s*\n(.*?)\n\s*```", response, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass

        # Try to find raw JSON object
        brace_matches = list(re.finditer(r"\{", response))
        for match in reversed(brace_matches):
            start = match.start()
            try:
                data = json.loads(response[start:])
                if "findings" in data or "summary" in data:
                    return data
            except (json.JSONDecodeError, ValueError):
                continue

        # Return the raw response wrapped in a structure
        return {
            "findings": [],
            "summary": {
                "total_findings": 0,
                "parse_error": "Could not extract structured JSON from agent response",
            },
            "raw_response": response,
            "reasoning_log": response,
        }
