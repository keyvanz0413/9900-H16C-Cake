"""Draft reply strategy tool.

This module keeps reply drafting tool-driven without sending emails. It gathers
the target thread context, checks writing style readiness, and returns a
structured strategy that the agent can use to write the final draft.
"""

from __future__ import annotations

import json
import re
from typing import Any

from .writing_style import get_writing_style_profile


_email_tool: Any | None = None
_memory_tool: Any | None = None


def configure_draft_reply(email_tool: Any | None = None, memory_tool: Any | None = None) -> None:
    """Attach provider tools used by get_draft_reply_strategy."""
    global _email_tool, _memory_tool
    _email_tool = email_tool
    _memory_tool = memory_tool


def get_draft_reply_strategy(
    user_request: str,
    contact_query: str = "",
    thread_query: str = "",
    email_id: str = "",
    reply_goal: str = "",
    include_writing_style: bool = True,
    allow_stale_style: bool = False,
    max_emails: int = 10,
) -> str:
    """Collect email context and return a structured reply strategy.

    Args:
        user_request: The user's drafting instruction.
        contact_query: Person or email address to search for.
        thread_query: Subject or thread keywords to search for.
        email_id: Exact email id if already known.
        reply_goal: Optional explicit goal such as confirm, decline, or clarify.
        include_writing_style: Whether to include saved writing style readiness.
        allow_stale_style: Whether a stale style profile can still be used.
        max_emails: Maximum related emails to search when email_id is unknown.

    Returns:
        JSON string with source context, reply strategy, writing style state,
        draft readiness, and safety notes. This tool is read-only.
    """
    max_emails = _clamp_int(max_emails, default=10, minimum=1, maximum=50)
    preflight_style = _get_style_context(
        include_writing_style=include_writing_style,
        recipient_query=contact_query,
        allow_stale_style=allow_stale_style,
    )
    preflight_block = _style_preflight_block(preflight_style, allow_stale_style)
    if preflight_block:
        return _blocked_strategy_text(
            _blocked_strategy_response(
                user_request=user_request,
                contact_query=contact_query,
                thread_query=thread_query,
                email_id=email_id,
                search_query=_build_search_query(user_request, contact_query, thread_query),
                style=preflight_style,
                readiness=preflight_block,
            )
        )

    raw_context, email_items = _load_thread_context(
        user_request=user_request,
        contact_query=contact_query,
        thread_query=thread_query,
        email_id=email_id,
        max_emails=max_emails,
    )
    selected_email = _select_email(email_items)
    sender = selected_email.get("sender", "")
    subject = selected_email.get("subject", "")
    detected_contact = contact_query or _name_from_sender(sender)
    detected_email = _email_from_sender(sender)
    style = preflight_style
    context_summary = _summarize_context(raw_context, selected_email)
    goal = _infer_goal(reply_goal, user_request, raw_context)
    readiness = _draft_readiness(raw_context, selected_email, style, allow_stale_style)
    contact_memory = _read_contact_memory(detected_email or detected_contact)

    result = {
        "intent": "draft_reply_strategy",
        "source": {
            "user_request": user_request,
            "contact_query": contact_query,
            "thread_query": thread_query,
            "email_id": email_id,
            "search_query": _build_search_query(user_request, contact_query, thread_query),
            "related_emails_found": _extract_total_count(raw_context, email_items),
        },
        "thread_context": {
            "sender": sender,
            "recipient_email": detected_email,
            "subject": subject,
            "latest_message_summary": context_summary,
            "detected_request": _detected_request(goal, raw_context),
            "important_details": _important_details(raw_context),
            "raw_email_included": False,
        },
        "reply_strategy": {
            "goal": goal,
            "tone": _strategy_tone(goal, style),
            "relationship_context": contact_memory or _relationship_context(sender),
            "key_points": _key_points(goal, user_request, raw_context),
            "avoid": _avoid_points(),
        },
        "writing_style": style,
        "draft_readiness": readiness,
        "recommended_agent_action": _recommended_action(readiness),
        "safety_notes": [
            "No email has been sent.",
            "No provider draft has been created.",
            "Do not call send or reply unless the user explicitly confirms sending.",
        ],
    }
    return _to_json(result)


def _style_preflight_block(style: dict[str, Any], allow_stale_style: bool) -> dict[str, Any] | None:
    """Block drafting before context gathering when style requires user choice."""
    if not style.get("included"):
        return None
    profile_state = style.get("profile_state", "")
    if profile_state == "missing":
        return _blocked(
            "missing_writing_style",
            "I do not have a saved writing style profile yet. Would you like me to learn your style from recent sent emails before drafting?",
        )
    if profile_state == "stale" and not allow_stale_style:
        return _blocked(
            "stale_writing_style",
            "Your saved writing style profile has not been updated for more than 7 days. Would you like me to refresh it before drafting?",
        )
    return None


def _blocked_strategy_text(data: dict[str, Any]) -> str:
    """Render a blocked strategy as a final-answer instruction, not draft material."""
    return (
        "FINAL_RESPONSE_REQUIRED\n"
        "Do not call any more tools.\n"
        "Do not write an email draft.\n"
        "Return this exact question to the user:\n"
        f"{data.get('final_response', '')}\n\n"
        "Structured status:\n"
        f"{json.dumps(data, ensure_ascii=False, indent=2)}"
    )


def _blocked_strategy_response(
    user_request: str,
    contact_query: str,
    thread_query: str,
    email_id: str,
    search_query: str,
    style: dict[str, Any],
    readiness: dict[str, Any],
) -> dict[str, Any]:
    """Return a blocking response without draftable strategy details."""
    question = readiness.get("user_question", "")
    return {
        "intent": "draft_reply_strategy",
        "tool_result_type": "final_response_required",
        "final_response_required": True,
        "do_not_call_more_tools": True,
        "do_not_draft": True,
        "final_response": question,
        "source": {
            "user_request": user_request,
            "contact_query": contact_query,
            "thread_query": thread_query,
            "email_id": email_id,
            "search_query": search_query,
            "related_emails_found": 0,
        },
        "thread_context": {
            "sender": "",
            "recipient_email": "",
            "subject": "",
            "latest_message_summary": "",
            "detected_request": "",
            "important_details": [],
            "raw_email_included": False,
        },
        "reply_strategy": {
            "goal": "",
            "tone": "",
            "relationship_context": "",
            "key_points": [],
            "avoid": _avoid_points(),
        },
        "writing_style": style,
        "draft_readiness": readiness,
        "must_not_draft": True,
        "recommended_agent_action": question,
        "safety_notes": [
            "No email has been sent.",
            "No provider draft has been created.",
            "Do not write draft text until draft_readiness.ready_to_draft is true.",
            "Do not call search_emails, get_email_body, send, or reply after this blocked result.",
            "Return final_response to the user now.",
        ],
    }


def _load_thread_context(
    user_request: str,
    contact_query: str,
    thread_query: str,
    email_id: str,
    max_emails: int,
) -> tuple[str, list[dict[str, Any]]]:
    """Load the exact email body or search for related thread context."""
    if _email_tool is None:
        return "", []

    if email_id and hasattr(_email_tool, "get_email_body"):
        raw_body = _safe_call(lambda: _email_tool.get_email_body(email_id=email_id), fallback="")
        item = _parse_email_body(raw_body, email_id)
        return raw_body, [item] if item else []

    query = _build_search_query(user_request, contact_query, thread_query)
    if not query:
        query = "newer_than:30d"
    raw_result = _safe_call(lambda: _email_tool.search_emails(query=query, max_results=max_emails), fallback="")
    return raw_result, _parse_provider_email_list(raw_result)


def _build_search_query(user_request: str, contact_query: str, thread_query: str) -> str:
    """Build a provider search query from user and agent hints."""
    parts = []
    if contact_query:
        parts.append(contact_query)
    if thread_query:
        parts.append(thread_query)
    if not parts:
        quoted = re.findall(r'"([^"]+)"', user_request)
        parts.extend(quoted[:2])
    if not parts and any(term in user_request.lower() for term in ("meeting", "join", "on time")):
        parts.append("meeting")
    return " ".join(part.strip() for part in parts if part.strip())


def _parse_provider_email_list(raw: str) -> list[dict[str, Any]]:
    """Parse provider search results into lightweight email records."""
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in raw.splitlines():
        item_match = re.match(r"\s*(\d+)\.\s*(?:\[UNREAD\]\s*)?From:\s*(.+)", line)
        if item_match:
            if current:
                items.append(current)
            current = {
                "index": int(item_match.group(1)),
                "sender": item_match.group(2).strip(),
                "subject": "",
                "date": "",
                "preview": "",
                "id": "",
            }
            continue

        if current is None:
            continue

        stripped = line.strip()
        for key, prefix in (
            ("subject", "Subject:"),
            ("date", "Date:"),
            ("preview", "Preview:"),
            ("id", "ID:"),
        ):
            if stripped.startswith(prefix):
                current[key] = stripped[len(prefix):].strip()
                break

    if current:
        items.append(current)
    return items


def _parse_email_body(raw: str, email_id: str) -> dict[str, Any]:
    """Parse a provider email body response into a lightweight record."""
    result = {
        "index": 1,
        "sender": _line_value(raw, "From:"),
        "subject": _line_value(raw, "Subject:"),
        "date": _line_value(raw, "Date:"),
        "preview": _body_preview(raw),
        "id": email_id,
    }
    return result if any(result.values()) else {}


def _line_value(raw: str, prefix: str) -> str:
    """Read a single header-style line value."""
    for line in raw.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return ""


def _body_preview(raw: str) -> str:
    """Return a short sanitized preview from an email body response."""
    marker = "--- Email Body ---"
    body = raw.split(marker, 1)[1] if marker in raw else raw
    body = re.sub(r"\s+", " ", body).strip()
    return body[:300]


def _select_email(email_items: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the latest/relevant parsed email record."""
    return email_items[0] if email_items else {}


def _get_style_context(
    include_writing_style: bool,
    recipient_query: str,
    allow_stale_style: bool,
) -> dict[str, Any]:
    """Read the writing style profile state for draft readiness."""
    if not include_writing_style:
        return {
            "included": False,
            "profile_state": "disabled",
            "confidence": "none",
            "profile": {},
            "allow_stale_style": allow_stale_style,
        }

    try:
        style = json.loads(get_writing_style_profile(recipient_query=recipient_query))
    except Exception as exc:  # pragma: no cover - defensive around tool wiring
        return {
            "included": True,
            "profile_state": "unavailable",
            "confidence": "low",
            "profile": {},
            "error": str(exc),
            "allow_stale_style": allow_stale_style,
        }

    profile = style.get("profile", {})
    return {
        "included": True,
        "profile_state": style.get("profile_state", "unavailable"),
        "confidence": style.get("confidence", "low"),
        "profile": {
            "tone": profile.get("tone", ""),
            "greeting_patterns": profile.get("greeting_patterns", []),
            "sign_off_patterns": profile.get("sign_off_patterns", []),
            "structure": profile.get("structure", []),
            "avoid": profile.get("avoid", []),
        },
        "source": style.get("source", {}),
        "allow_stale_style": allow_stale_style,
    }


def _draft_readiness(
    raw_context: str,
    selected_email: dict[str, Any],
    style: dict[str, Any],
    allow_stale_style: bool,
) -> dict[str, Any]:
    """Decide whether the agent may write the draft now."""
    if _email_tool is None:
        return _blocked("missing_thread_context", "No email provider is configured.")
    if not raw_context.strip() or not selected_email:
        return _blocked("missing_thread_context", "I could not identify which email thread to reply to.")

    profile_state = style.get("profile_state", "")
    if style.get("included"):
        if profile_state == "missing":
            return _blocked(
                "missing_writing_style",
                "I do not have a saved writing style profile yet. Would you like me to learn your style from recent sent emails before drafting?",
            )
        if profile_state == "stale" and not allow_stale_style:
            return _blocked(
                "stale_writing_style",
                "Your saved writing style profile has not been updated for more than 7 days. Would you like me to refresh it before drafting?",
            )

    return {
        "state": "ready",
        "ready_to_draft": True,
        "blocked_by": "",
        "user_question": "",
        "needs_user_confirmation_before_send": True,
    }


def _blocked(blocked_by: str, user_question: str) -> dict[str, Any]:
    """Return a blocked draft readiness object."""
    return {
        "state": blocked_by,
        "ready_to_draft": False,
        "blocked_by": blocked_by,
        "user_question": user_question,
        "needs_user_confirmation_before_send": True,
    }


def _infer_goal(reply_goal: str, user_request: str, raw_context: str) -> str:
    """Infer the strategic goal of the reply."""
    explicit = reply_goal.strip().lower()
    if explicit:
        return explicit

    lowered = f"{user_request} {raw_context}".lower()
    if any(term in lowered for term in ("join", "on time", "works for me", "confirm", "yes", "attend")):
        return "confirm"
    if any(term in lowered for term in ("can't", "cannot", "decline", "not available", "won't")):
        return "decline"
    if any(term in lowered for term in ("clarify", "question", "what do you mean")):
        return "clarify"
    if any(term in lowered for term in ("later", "delay", "tomorrow", "next week")):
        return "delay"
    if any(term in lowered for term in ("propose", "schedule", "available")):
        return "propose_next_step"
    return "provide_information"


def _summarize_context(raw_context: str, selected_email: dict[str, Any]) -> str:
    """Create a short, non-raw summary of the target email."""
    preview = selected_email.get("preview", "")
    subject = selected_email.get("subject", "")
    if preview:
        return _sentence(f"The email says: {preview}")
    if subject:
        return f"The related thread subject is '{subject}'."
    if raw_context.strip():
        return "Related email context was found, but no concise preview was available."
    return ""


def _detected_request(goal: str, raw_context: str) -> str:
    """Describe what the sender appears to want."""
    lowered = raw_context.lower()
    if goal == "confirm" and "meeting" in lowered:
        return "Confirm attendance for the meeting."
    if goal == "decline":
        return "Respond that the requested item does not work."
    if goal == "clarify":
        return "Ask for clarification."
    if goal == "delay":
        return "Acknowledge and provide a later timeline."
    if goal == "propose_next_step":
        return "Propose a concrete next step."
    return "Provide the requested information or acknowledgement."


def _important_details(raw_context: str) -> list[str]:
    """Extract useful details to carry into the draft."""
    details: list[str] = []
    lowered = raw_context.lower()
    if "meeting" in lowered:
        details.append("meeting")
    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", raw_context, re.IGNORECASE)
    if time_match:
        details.append(f"time: {time_match.group(0)}")
    day_match = re.search(r"\b(this|next)?\s*(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b", raw_context, re.IGNORECASE)
    if day_match:
        details.append(f"day: {day_match.group(0).strip()}")
    return details[:5]


def _key_points(goal: str, user_request: str, raw_context: str) -> list[str]:
    """Return key points the final draft should include."""
    points: list[str] = []
    if goal == "confirm":
        points.append("thank them or acknowledge the message")
        if any(term in f"{user_request} {raw_context}".lower() for term in ("join", "attend", "meeting")):
            points.append("confirm that the user will join the meeting on time")
        else:
            points.append("clearly confirm the requested item")
    elif goal == "decline":
        points.extend(["thank them", "politely decline", "offer an alternative if useful"])
    elif goal == "clarify":
        points.extend(["acknowledge their message", "ask one clear clarification question"])
    elif goal == "delay":
        points.extend(["acknowledge their message", "give a clear later timeline"])
    elif goal == "propose_next_step":
        points.extend(["acknowledge their message", "propose a concrete next step"])
    else:
        points.extend(["acknowledge their message", "provide the requested information"])

    details = _important_details(raw_context)
    if details:
        points.append(f"include relevant detail(s): {', '.join(details)}")
    return points


def _strategy_tone(goal: str, style: dict[str, Any]) -> str:
    """Choose a reply tone from strategy and style profile."""
    profile_tone = style.get("profile", {}).get("tone", "")
    if profile_tone and style.get("profile_state") in ("fresh", "refreshed", "stale"):
        return profile_tone
    if goal in ("decline", "clarify"):
        return "polite and careful"
    return "polite and concise"


def _relationship_context(sender: str) -> str:
    """Describe relationship from available sender context."""
    if sender:
        return "known contact from the selected email thread"
    return "relationship context unavailable"


def _read_contact_memory(contact: str) -> str:
    """Read contact memory when available."""
    if not contact or _memory_tool is None or not hasattr(_memory_tool, "read_memory"):
        return ""
    result = _safe_call(lambda: _memory_tool.read_memory(f"contact:{contact}"), fallback="")
    if not result or "not found" in result.lower():
        return ""
    return result


def _avoid_points() -> list[str]:
    """Return safety constraints for the final draft."""
    return [
        "claiming the email has been sent",
        "adding unavailable details",
        "over-explaining",
        "copying unrelated prior email wording",
    ]


def _recommended_action(readiness: dict[str, Any]) -> str:
    """Tell the agent what to do next."""
    if readiness.get("ready_to_draft"):
        return "Write a draft using reply_strategy and writing_style. State that it has not been sent."
    if readiness.get("user_question"):
        return readiness["user_question"]
    return "Ask the user for the missing context before drafting."


def _extract_total_count(raw: str, items: list[dict[str, Any]]) -> int:
    """Read the provider's total count, falling back to parsed item count."""
    match = re.search(r"Found\s+(\d+)\s+email", raw, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return len(items)


def _name_from_sender(sender: str) -> str:
    """Extract a display name from a sender string."""
    if "<" in sender:
        return sender.split("<", 1)[0].strip()
    return sender.strip()


def _email_from_sender(sender: str) -> str:
    """Extract an email address from a sender string."""
    match = re.search(r"<([^>]+)>", sender)
    if match:
        return match.group(1).strip()
    match = re.search(r"[\w.+-]+@[\w.-]+", sender)
    return match.group(0) if match else ""


def _sentence(text: str) -> str:
    """Keep a summary readable and bounded."""
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned[:260]


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Convert a value to int and keep it inside a safe range."""
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _safe_call(callable_obj: Any, fallback: str) -> str:
    """Call a provider function safely and convert the result to text."""
    try:
        result = callable_obj()
    except Exception as exc:  # pragma: no cover - defensive around provider tools
        return fallback or f"Error: {exc}"
    return str(result)


def _to_json(data: dict[str, Any]) -> str:
    """Serialize the structured strategy result for the agent."""
    return json.dumps(data, ensure_ascii=False, indent=2)
