"""Message history and token budget management for the agent loop."""

from __future__ import annotations

import json


# Rough token estimates (conservative — 1 token ≈ 4 chars)
def _estimate_tokens(text: str) -> int:
    return len(text) // 4 + 1


def _message_tokens(msg: dict) -> int:
    content = msg.get("content", "")
    if isinstance(content, str):
        return _estimate_tokens(content)
    if isinstance(content, list):
        total = 0
        for block in content:
            if isinstance(block, dict):
                total += _estimate_tokens(json.dumps(block))
            else:
                total += _estimate_tokens(str(block))
        return total
    return 0


class MessageHistory:
    """Manages conversation messages with a token budget.

    When the total estimated tokens exceed the budget, older tool-result
    messages are summarized to free space while preserving the system
    context and most recent exchanges.
    """

    def __init__(self, max_tokens: int = 180_000):
        self.messages: list[dict] = []
        self.max_tokens = max_tokens

    def add(self, message: dict) -> None:
        self.messages.append(message)
        self._trim_if_needed()

    def add_many(self, messages: list[dict]) -> None:
        self.messages.extend(messages)
        self._trim_if_needed()

    def get_messages(self) -> list[dict]:
        return list(self.messages)

    def total_tokens(self) -> int:
        return sum(_message_tokens(m) for m in self.messages)

    def _trim_if_needed(self) -> None:
        """Summarize old tool results if over budget."""
        if self.total_tokens() <= self.max_tokens:
            return

        # Find tool_result blocks older than the last 6 messages and truncate them
        keep_recent = 6
        for i in range(len(self.messages) - keep_recent):
            msg = self.messages[i]
            if msg.get("role") != "user":
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            for j, block in enumerate(content):
                if isinstance(block, dict) and block.get("type") == "tool_result":
                    text = block.get("content", "")
                    if isinstance(text, str) and len(text) > 500:
                        block["content"] = text[:200] + "\n...[truncated]..."

            if self.total_tokens() <= self.max_tokens:
                return
