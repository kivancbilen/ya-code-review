"""Protocol for reasoning templates."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ReasoningTemplate(Protocol):
    """A template that constructs prompts for semi-formal reasoning."""

    @property
    def name(self) -> str:
        """Template identifier."""
        ...

    def build_system_prompt(self) -> str:
        """Return the system prompt for the agent."""
        ...

    def build_user_message(self, **kwargs: str) -> str:
        """Build the user message with task-specific context injected."""
        ...

    def parse_response(self, response: str) -> dict:
        """Parse the agent's final response into structured data."""
        ...
