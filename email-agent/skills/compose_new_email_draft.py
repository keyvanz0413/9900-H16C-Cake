"""Compose a brand-new outbound email draft.

This skill only gathers writing-style context and sender identity. It never
sends or modifies mailbox state. The actual composition and staging of the
email is done by the main agent (so the Gmail approval plugin's confirmation
flow runs and the user approves the email before it leaves the outbox).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable


DEFAULT_WRITING_STYLE_CONTENT = "# Writing Style\n\n- No writing style profile yet."


def _build_key_points_question(*, recipient: str, topic: str) -> str:
    recipient_text = recipient or "the recipient"
    topic_text = topic or "this topic"
    return (
        f"Before I draft the email to {recipient_text} about {topic_text}, "
        "what key points should I include? For example: the main purpose, the specific ask, "
        "timing, location, deadline, links, or any attachments to mention."
    )


def _resolve_writing_style_path(skill_runtime: dict[str, Any] | None) -> Path:
    runtime = skill_runtime or {}
    paths = runtime.get("paths") or {}
    raw_path = paths.get("writing_style_markdown")
    if raw_path:
        return Path(raw_path)
    return Path(__file__).resolve().parent.parent / "WRITING_STYLE.md"


def _read_writing_style_markdown(skill_runtime: dict[str, Any] | None) -> tuple[Path, str]:
    writing_style_path = _resolve_writing_style_path(skill_runtime)
    if not writing_style_path.exists():
        return writing_style_path, DEFAULT_WRITING_STYLE_CONTENT

    content = writing_style_path.read_text(encoding="utf-8").strip()
    if not content:
        return writing_style_path, DEFAULT_WRITING_STYLE_CONTENT
    return writing_style_path, content


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> str:
    print(f"[skill:compose_new_email_draft] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:compose_new_email_draft] finished {name}", flush=True)
    return text


def execute_skill(*, arguments, used_tools, skill_spec, skill_runtime=None):
    recipient = str(arguments.get("recipient") or "").strip()
    topic = str(arguments.get("topic") or "").strip()
    key_points = str(arguments.get("key_points") or "").strip()

    if not key_points:
        print(
            f"[skill:compose_new_email_draft] missing key_points for recipient={recipient or '(empty)'} "
            f"topic={topic or '(empty)'}",
            flush=True,
        )
        return {
            "completed": True,
            "response": _build_key_points_question(recipient=recipient, topic=topic),
            "reason": "Need user-provided key points before drafting a brand-new outbound email.",
            "session_state_update": {
                "outbound_email_state": {
                    "phase": "collecting_details",
                    "recipient": recipient,
                    "topic": topic,
                }
            },
        }

    identity_text = "(sender identity unavailable - infer sign-off from WRITING_STYLE)"
    if "get_my_identity" in used_tools:
        identity_text = _call_tool(
            "get_my_identity",
            used_tools["get_my_identity"],
            {},
        )

    writing_style_path, writing_style_markdown = _read_writing_style_markdown(skill_runtime)

    print(
        f"[skill:compose_new_email_draft] recipient={recipient or '(empty)'} "
        f"topic={topic or '(empty)'} key_points_len={len(key_points)}",
        flush=True,
    )

    lines = [
        "[COMPOSE_NEW_EMAIL_DRAFT_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'compose_new_email_draft')}",
        f"recipient: {recipient or '(not provided)'}",
        f"topic: {topic or '(not provided)'}",
        f"key_points: {key_points or '(none)'}",
        "",
        "[HANDOFF_INSTRUCTIONS]",
        "This skill only gathered writing style and sender identity. The MAIN AGENT must now:",
        "1. Compose the full email body using the recipient, topic, and key_points above,",
        "   mirroring the tone and sign-off from [WRITING_STYLE] and signing with the display",
        "   name in [SENDER_IDENTITY].",
        "2. Derive a concise subject from the topic if one is not explicitly given.",
        "3. Call the send tool with to=<recipient>, subject=<derived subject>, body=<composed body>.",
        "   The Gmail approval plugin will stage the email and present the draft to the user.",
        "4. NEVER claim the email has been sent until the user explicitly confirms in a later turn.",
        "   Staging is not sending.",
        "5. If recipient or topic is missing, ask the user for the missing detail INSTEAD of calling send.",
        "",
        "[WRITING_STYLE]",
        f"path: {writing_style_path}",
        writing_style_markdown,
        "",
        "[SENDER_IDENTITY]",
        identity_text,
    ]

    return {
        "completed": False,
        "response": "\n".join(lines).strip(),
        "reason": (
            "Compose context prepared (writing style + sender identity). "
            "Main agent must draft the body and call send so the approval plugin can stage it for user confirmation."
        ),
    }
