"""Core agent loop: messages.create → tool_use → dispatch → loop."""

from __future__ import annotations

from typing import Callable

import anthropic

from fb_review_agent.agent.context import MessageHistory
from fb_review_agent.agent.tools import TOOL_DEFINITIONS, dispatch_tool
from fb_review_agent.config import Config


def run_agent_loop(
    system_prompt: str,
    user_message: str,
    config: Config,
    repo_root: str,
    on_tool_call: Callable[[str, dict], None] | None = None,
    on_thinking: Callable[[str], None] | None = None,
    tools: list[dict] | None = None,
    model_override: str | None = None,
) -> str:
    """Run the tool-use agent loop until the model produces a final text response.

    Args:
        tools: Tool definitions to use. Defaults to TOOL_DEFINITIONS.
        model_override: Override config.model for this run.

    Returns the final assistant text content.
    """
    client = anthropic.Anthropic(api_key=config.get_api_key())
    history = MessageHistory(max_tokens=config.max_context_tokens)
    history.add({"role": "user", "content": user_message})

    effective_tools = tools if tools is not None else TOOL_DEFINITIONS
    effective_model = model_override or config.model

    for turn in range(config.max_turns):
        response = client.messages.create(
            model=effective_model,
            max_tokens=16_384,
            system=system_prompt,
            tools=effective_tools,
            messages=history.get_messages(),
        )

        # Build the assistant message from response content
        assistant_content = []
        text_parts = []
        tool_uses = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
                assistant_content.append({"type": "text", "text": block.text})
            elif block.type == "tool_use":
                tool_uses.append(block)
                assistant_content.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        history.add({"role": "assistant", "content": assistant_content})

        # If no tool calls, we're done — return the text
        if not tool_uses:
            return "\n".join(text_parts)

        # Dispatch each tool call and collect results
        tool_results = []
        for tool_use in tool_uses:
            if on_tool_call:
                on_tool_call(tool_use.name, tool_use.input)

            result = dispatch_tool(tool_use.name, tool_use.input, repo_root)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": tool_use.id,
                "content": result,
            })

        history.add({"role": "user", "content": tool_results})

        # If stop_reason is end_turn with text, we're done
        if response.stop_reason == "end_turn" and text_parts and not tool_uses:
            return "\n".join(text_parts)

    return "\n".join(text_parts) if text_parts else "(agent reached max turns without final response)"
