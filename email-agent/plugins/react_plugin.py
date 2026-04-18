"""
Local ReAct plugin that follows the project's configured AGENT_MODEL.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import connectonion
from connectonion.core.events import after_user_input, after_tools
from connectonion.llm_do import llm_do

if TYPE_CHECKING:
    from connectonion.core.agent import Agent


MODEL_NAME = os.getenv("AGENT_MODEL", "co/claude-sonnet-4-5")
PROMPT_ROOT = Path(connectonion.__file__).resolve().parent / "prompt_files"
ACKNOWLEDGE_PROMPT = PROMPT_ROOT / "react_acknowledge.md"
REFLECT_PROMPT = PROMPT_ROOT / "reflect.md"


def _format_conversation(
    messages: list,
    max_tokens: int = 4000,
    max_messages: int = 50,
) -> str:
    """Format conversation history with smart truncation."""
    max_chars = max_tokens * 4

    recent = messages[-max_messages:] if len(messages) > max_messages else messages
    if not recent:
        return ""

    total_chars = sum(len(m.get("content", "")) for m in recent)
    if total_chars <= max_chars:
        lines = []
        for msg in recent:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    user_chars = sum(len(m.get("content", "")) for m in recent if m.get("role") == "user")
    available_for_assistant = max_chars - user_chars

    assistant_msgs = [m for m in recent if m.get("role") == "assistant" and m.get("content")]
    if not assistant_msgs:
        return "\n".join(f"user: {m.get('content', '')}" for m in recent if m.get("role") == "user")

    count = len(assistant_msgs)
    weights = [1 + (index / count) for index in range(count)]
    total_weight = sum(weights)
    char_budgets = [int(available_for_assistant * weight / total_weight) for weight in weights]

    lines = []
    assistant_idx = 0
    for msg in recent:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if not content:
            continue

        if role == "user":
            lines.append(f"user: {content}")
        elif role == "assistant":
            budget = char_budgets[assistant_idx] if assistant_idx < len(char_budgets) else 200
            assistant_idx += 1
            if len(content) > budget:
                content = content[:budget] + "..."
            lines.append(f"assistant: {content}")

    return "\n".join(lines)


def _compress_messages(messages: list[dict], tool_result_limit: int = 150) -> str:
    """Compress conversation history for the reflection step."""
    lines = []

    for msg in messages:
        role = msg["role"]

        if role == "user":
            lines.append(f"USER: {msg['content']}")
        elif role == "assistant":
            if "tool_calls" in msg:
                tools = [
                    f"{tool_call['function']['name']}({tool_call['function']['arguments']})"
                    for tool_call in msg["tool_calls"]
                ]
                lines.append(f"ASSISTANT: {', '.join(tools)}")
            else:
                lines.append(f"ASSISTANT: {msg['content']}")
        elif role == "tool":
            result = msg["content"]
            if len(result) > tool_result_limit:
                result = result[:tool_result_limit] + "..."
            lines.append(f"TOOL: {result}")

    return "\n".join(lines)


@after_user_input
def acknowledge_request(agent: "Agent") -> None:
    """Immediately acknowledge the user's request to show we understood."""
    user_prompt = agent.current_session.get("user_prompt", "")
    if not user_prompt:
        return

    messages = agent.current_session.get("messages", [])
    conversation = _format_conversation(messages)

    prompt = f"""Conversation so far:
{conversation}

Current user input: {user_prompt}

Acknowledge this request (1-2 sentences):"""

    agent.logger.print(f"[dim]/understanding ({MODEL_NAME})...[/dim]")

    ack = llm_do(
        prompt,
        model=MODEL_NAME,
        temperature=0.3,
        system_prompt=ACKNOWLEDGE_PROMPT,
    )

    agent.current_session["intent"] = ack
    agent._record_trace({
        "type": "thinking",
        "kind": "intent",
        "content": ack,
    })
    agent.current_session["messages"].append({
        "role": "assistant",
        "content": ack,
    })


@after_tools
def reflect(agent: "Agent") -> None:
    """Reflect once after a tool batch finishes."""
    if agent.current_session.get("halt_turn") or agent.current_session.get("stop_signal"):
        return

    trace = agent.current_session["trace"][-1]
    if trace["type"] != "tool_result":
        return

    user_prompt = agent.current_session.get("user_prompt", "")
    tool_name = trace["name"]
    tool_args = trace["args"]
    status = trace["status"]
    conversation = _compress_messages(agent.current_session["messages"])

    if status == "success":
        tool_result = trace["result"]
        prompt = f"""Context:
{conversation}

Current:
User asked: {user_prompt}
Action: {tool_name}({tool_args})
Result: {str(tool_result)[:300]}"""
    else:
        error = trace.get("error", "Unknown error")
        prompt = f"""Context:
{conversation}

Current:
User asked: {user_prompt}
Action: {tool_name}({tool_args})
Error: {error}"""

    reasoning = llm_do(
        prompt,
        model=MODEL_NAME,
        temperature=0.2,
        system_prompt=REFLECT_PROMPT,
    )

    agent.logger.print(f"[dim]/reflecting ({MODEL_NAME})...[/dim]")
    agent._record_trace({
        "type": "thinking",
        "kind": "reflect",
        "content": reasoning,
    })
    agent.current_session["messages"].append({
        "role": "assistant",
        "content": reasoning,
    })


re_act = [acknowledge_request, reflect]
