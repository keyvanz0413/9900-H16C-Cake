"""Meeting scheduling context tool.

This module keeps meeting scheduling assistance read-only. It gathers email,
calendar, and memory context, then returns structured JSON so the agent can
recommend slots or draft replies without prematurely sending emails or creating
calendar events.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any


_email_tool: Any | None = None
_calendar_tool: Any | None = None
_memory_tool: Any | None = None

_WEEKDAY_INDEX = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


def configure_meeting_schedule(
    email_tool: Any | None = None,
    calendar_tool: Any | None = None,
    memory_tool: Any | None = None,
) -> None:
    """Attach provider tools used by get_meeting_schedule_context."""
    global _email_tool, _calendar_tool, _memory_tool
    _email_tool = email_tool
    _calendar_tool = calendar_tool
    _memory_tool = memory_tool


def get_meeting_schedule_context(
    contact_query: str = "",
    thread_query: str = "",
    requested_date: str = "",
    requested_time: str = "",
    duration_minutes: int = 30,
    days_ahead: int = 7,
    max_emails: int = 10,
) -> str:
    """Collect structured context for scheduling a meeting.

    Args:
        contact_query: Person, email address, or relationship mentioned by the user.
        thread_query: Subject or thread context to search for.
        requested_date: Explicit or relative meeting date from the user, if known.
        requested_time: Meeting time from the user, if known.
        duration_minutes: Desired meeting duration.
        days_ahead: Calendar lookahead window when no exact date is known.
        max_emails: Maximum related emails to search.

    Returns:
        JSON string containing contact, thread, agreement, calendar, status, and
        safety context. This tool is read-only.
    """
    duration_minutes = _clamp_int(duration_minutes, default=30, minimum=15, maximum=240)
    days_ahead = _clamp_int(days_ahead, default=7, minimum=1, maximum=60)
    max_emails = _clamp_int(max_emails, default=10, minimum=1, maximum=50)

    normalized_date = _normalize_date(requested_date)
    normalized_time = _normalize_time(requested_time)
    query = _build_email_query(contact_query, thread_query)

    raw_emails = ""
    email_items: list[dict[str, Any]] = []
    if _email_tool is not None:
        raw_emails = _safe_call(
            lambda: _email_tool.search_emails(query=query, max_results=max_emails),
            fallback="",
        )
        email_items = _parse_provider_email_list(raw_emails)

    haystack = _combined_text(contact_query, thread_query, requested_date, requested_time, raw_emails)
    resolved_contact = _resolve_contact(contact_query, raw_emails, email_items)
    proposed_times = _extract_proposed_times(haystack, normalized_date, normalized_time)

    if not normalized_date:
        normalized_date = _first_value(proposed_times, "date")
    if not normalized_time:
        normalized_time = _first_value(proposed_times, "time")

    contact_memory = _read_contact_memory(resolved_contact)
    calendar_context = _get_calendar_context(
        requested_date=normalized_date,
        requested_time=normalized_time,
        duration_minutes=duration_minutes,
        days_ahead=days_ahead,
    )
    agreement = _build_agreement(
        contact=resolved_contact,
        requested_date=normalized_date,
        requested_time=normalized_time,
        haystack=haystack,
        calendar_context=calendar_context,
    )
    status, calendar_action = _derive_status_and_action(agreement, calendar_context, wants_draft=bool(requested_time))

    result = {
        "intent": "meeting_schedule",
        "contact": resolved_contact,
        "request": {
            "requested_date": normalized_date,
            "requested_time": normalized_time,
            "duration_minutes": duration_minutes,
            "days_ahead": days_ahead,
        },
        "thread_context": {
            "query": query,
            "related_emails_found": _extract_total_count(raw_emails, email_items),
            "latest_subject": email_items[0]["subject"] if email_items else "",
            "summary": _summarize_thread(email_items),
            "proposed_times": proposed_times,
            "raw_email_result": raw_emails,
        },
        "calendar": calendar_context,
        "agreement": agreement,
        "status": status,
        "calendar_action": calendar_action,
        "missing_requirements": _missing_requirements(agreement),
        "evidence": _extract_evidence(raw_emails, haystack),
        "contact_memory": contact_memory,
        "recommended_action": _recommended_action(status, calendar_action, normalized_date, normalized_time),
        "safety_notes": [
            "No email has been sent.",
            "No calendar event has been created.",
            "Only report a meeting as booked after a calendar event exists or a write tool succeeds.",
        ],
    }
    return _to_json(result)


def create_confirmed_meeting(
    meeting_context_json: str,
    title: str = "",
    create_meet_link: bool = False,
) -> str:
    """Create a calendar event from confirmed meeting context.

    This is a write-action wrapper. The agent should call it only after the user
    explicitly confirms that the email-confirmed meeting should be added to
    calendar.

    Args:
        meeting_context_json: JSON returned by get_meeting_schedule_context.
        title: Optional calendar title. A default title is generated if empty.
        create_meet_link: Whether to create a Google Meet event instead of a
            regular calendar event.

    Returns:
        JSON string describing success, already-existing event, validation
        failure, or provider failure.
    """
    context, error = _load_context(meeting_context_json)
    if error:
        return _write_result(
            status="write_action_failed",
            calendar_action="creation_failed",
            error=error,
        )

    validation_error = _validate_ready_to_create(context)
    if validation_error:
        return _write_result(
            status=context.get("status", "needs_more_context"),
            calendar_action="do_not_create_yet",
            error=validation_error,
            context_summary=_context_summary(context),
        )

    if _calendar_tool is None:
        return _write_result(
            status="write_action_failed",
            calendar_action="creation_failed",
            error="No calendar provider tool is configured.",
            context_summary=_context_summary(context),
        )

    request = context.get("request", {})
    contact = context.get("contact", {})
    requested_date = str(request.get("requested_date", ""))
    requested_time = str(request.get("requested_time", ""))
    duration_minutes = _clamp_int(request.get("duration_minutes", 30), default=30, minimum=15, maximum=240)
    start_time = _join_start_time(requested_date, requested_time)
    end_time = _calculate_end_time(start_time, duration_minutes)
    attendees = str(contact.get("email", ""))
    event_title = title.strip() or _default_meeting_title(contact, context)

    calendar_context = _get_calendar_context(
        requested_date=requested_date,
        requested_time=requested_time,
        duration_minutes=duration_minutes,
        days_ahead=_clamp_int(request.get("days_ahead", 7), default=7, minimum=1, maximum=60),
    )
    if calendar_context.get("matching_event_found"):
        return _write_result(
            status="calendar_confirmed",
            calendar_action="already_exists",
            title=event_title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            raw_result=calendar_context.get("raw_events", ""),
            context_summary=_context_summary(context),
        )

    description = _meeting_description(context)
    if create_meet_link:
        if not attendees:
            return _write_result(
                status="write_action_failed",
                calendar_action="creation_failed",
                error="Cannot create a Google Meet without attendee email addresses.",
                context_summary=_context_summary(context),
            )
        raw_result = _safe_call(
            lambda: _calendar_tool.create_meet(
                title=event_title,
                start_time=start_time,
                end_time=end_time,
                attendees=attendees,
                description=description,
            ),
            fallback="",
        )
    else:
        raw_result = _safe_call(
            lambda: _calendar_tool.create_event(
                title=event_title,
                start_time=start_time,
                end_time=end_time,
                attendees=attendees or None,
                description=description,
            ),
            fallback="",
        )

    if raw_result.startswith("Error:"):
        return _write_result(
            status="write_action_failed",
            calendar_action="creation_failed",
            title=event_title,
            start_time=start_time,
            end_time=end_time,
            attendees=attendees,
            error=raw_result,
            context_summary=_context_summary(context),
        )

    return _write_result(
        status="write_action_succeeded",
        calendar_action="created",
        title=event_title,
        start_time=start_time,
        end_time=end_time,
        attendees=attendees,
        raw_result=raw_result,
        context_summary=_context_summary(context),
    )


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
        return f"Error: {exc}"
    return str(result)


def _build_email_query(contact_query: str, thread_query: str) -> str:
    """Build a provider search query from user contact/thread hints."""
    parts = [part.strip() for part in (contact_query, thread_query) if part and part.strip()]
    if parts:
        return " OR ".join(parts)
    return "meeting OR schedule OR availability OR \"coffee chat\" OR call"


def _parse_provider_email_list(raw: str) -> list[dict[str, Any]]:
    """Parse the text returned by read/search email tools into email records."""
    items: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None

    for line in raw.splitlines():
        item_match = re.match(r"\s*(\d+)\.\s*(\[UNREAD\]\s*)?From:\s*(.+)", line)
        if item_match:
            if current:
                items.append(current)
            current = {
                "index": int(item_match.group(1)),
                "unread": bool(item_match.group(2)),
                "sender": item_match.group(3).strip(),
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


def _extract_total_count(raw: str, items: list[dict[str, Any]]) -> int:
    """Read the provider's total count, falling back to parsed item count."""
    match = re.search(r"Found\s+(\d+)\s+email", raw, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return len(items)


def _combined_text(*parts: str) -> str:
    """Join text fields into one lower-cased search space."""
    return " ".join(part for part in parts if part).lower()


def _resolve_contact(
    contact_query: str,
    raw_emails: str,
    email_items: list[dict[str, Any]],
) -> dict[str, str | bool]:
    """Resolve the participant from user input or related email senders."""
    query_email = _extract_email(contact_query)
    raw_email = _extract_email(raw_emails)
    sender = email_items[0]["sender"] if email_items else ""
    sender_email = _extract_email(sender)
    email = query_email or sender_email or raw_email
    name = _display_name(contact_query) or _display_name(sender) or email
    return {
        "query": contact_query,
        "email": email,
        "name": name,
        "source": "user_query" if query_email else "email_search" if email else "unresolved",
        "resolved": bool(email or contact_query.strip()),
    }


def _extract_email(text: str) -> str:
    """Extract the first email address from text."""
    match = re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", text or "")
    return match.group(0) if match else ""


def _display_name(text: str) -> str:
    """Extract a readable display name from a contact string."""
    if not text:
        return ""
    before_angle = text.split("<", 1)[0].strip().strip('"')
    if before_angle and "@" not in before_angle:
        return before_angle
    return ""


def _normalize_date(value: str) -> str:
    """Normalize common absolute or relative date strings to YYYY-MM-DD."""
    value = (value or "").strip()
    if not value:
        return ""

    parsed = _parse_absolute_date(value)
    if parsed:
        return parsed

    lowered = value.lower()
    today = datetime.now().date()
    if "tomorrow" in lowered:
        return (today + timedelta(days=1)).strftime("%Y-%m-%d")

    for name, weekday in _WEEKDAY_INDEX.items():
        if name in lowered:
            days_until = (weekday - today.weekday()) % 7
            if days_until == 0 or "next" in lowered:
                days_until = days_until or 7
            return (today + timedelta(days=days_until)).strftime("%Y-%m-%d")
    return value


def _parse_absolute_date(value: str) -> str:
    """Parse several common absolute date formats."""
    candidates = [value.strip()]
    current_year = datetime.now().year
    candidates.append(f"{value.strip()} {current_year}")

    for candidate in candidates:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(candidate, fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
    return ""


def _normalize_time(value: str) -> str:
    """Normalize common time strings to HH:MM when possible."""
    value = (value or "").strip()
    if not value:
        return ""
    match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm|AM|PM)?\b", value)
    if not match:
        return value
    hour = int(match.group(1))
    minute = int(match.group(2) or "0")
    suffix = (match.group(3) or "").lower()
    if suffix == "pm" and hour < 12:
        hour += 12
    if suffix == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return value
    return f"{hour:02d}:{minute:02d}"


def _extract_proposed_times(haystack: str, requested_date: str, requested_time: str) -> list[dict[str, str]]:
    """Collect simple proposed time hints from user input and email text."""
    proposed: list[dict[str, str]] = []
    if requested_date or requested_time:
        proposed.append({"date": requested_date, "time": requested_time, "source": "user_request"})

    time_match = re.search(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", haystack, re.IGNORECASE)
    if time_match and not requested_time:
        proposed.append({"date": requested_date, "time": _normalize_time(time_match.group(0)), "source": "email_thread"})
    return proposed


def _first_value(items: list[dict[str, str]], key: str) -> str:
    """Return the first non-empty value for a key in proposed time records."""
    for item in items:
        if item.get(key):
            return item[key]
    return ""


def _read_contact_memory(contact: dict[str, str | bool]) -> str:
    """Read contact memory when a memory provider and contact key are available."""
    if _memory_tool is None or not hasattr(_memory_tool, "read_memory"):
        return ""
    keys = []
    if contact.get("email"):
        keys.append(f"contact:{contact['email']}")
    if contact.get("name"):
        keys.append(f"contact:{contact['name']}")
    for key in keys:
        result = _safe_call(lambda key=key: _memory_tool.read_memory(key), fallback="")
        if result and "not found" not in result.lower() and not result.startswith("Error:"):
            return result
    return ""


def _get_calendar_context(
    requested_date: str,
    requested_time: str,
    duration_minutes: int,
    days_ahead: int,
) -> dict[str, Any]:
    """Fetch available slots and event context without writing calendar data."""
    context: dict[str, Any] = {
        "availability_checked": False,
        "available_slots": [],
        "conflicts": [],
        "matching_event_found": False,
        "raw_availability": "",
        "raw_events": "",
    }
    if _calendar_tool is None:
        return context

    if requested_date and hasattr(_calendar_tool, "find_free_slots"):
        raw_slots = _safe_call(
            lambda: _calendar_tool.find_free_slots(requested_date, duration_minutes=duration_minutes),
            fallback="",
        )
        context["availability_checked"] = True
        context["raw_availability"] = raw_slots
        context["available_slots"] = _parse_available_slots(raw_slots, requested_date)

    if hasattr(_calendar_tool, "list_events"):
        raw_events = _safe_call(lambda: _calendar_tool.list_events(days_ahead=days_ahead), fallback="")
        context["raw_events"] = raw_events
        context["matching_event_found"] = _matching_event_found(raw_events, requested_date, requested_time)
        context["conflicts"] = _extract_conflicts(raw_events, requested_date, requested_time)
    elif hasattr(_calendar_tool, "get_today_events"):
        context["raw_events"] = _safe_call(lambda: _calendar_tool.get_today_events(), fallback="")

    return context


def _parse_available_slots(raw_slots: str, requested_date: str) -> list[dict[str, str]]:
    """Parse simple slot-looking times from calendar provider text."""
    slots: list[dict[str, str]] = []
    for match in re.finditer(r"\b(\d{1,2}:\d{2})\b", raw_slots):
        start = match.group(1)
        if not any(slot["start"].endswith(start) for slot in slots):
            slots.append({"start": f"{requested_date} {start}".strip(), "end": ""})
    return slots[:10]


def _matching_event_found(raw_events: str, requested_date: str, requested_time: str) -> bool:
    """Detect whether calendar events mention the requested date and time."""
    lowered = raw_events.lower()
    if not raw_events.strip() or any(marker in lowered for marker in ("no events", "no upcoming", "found 0")):
        return False
    if requested_date and requested_date not in raw_events:
        return False
    if requested_time and requested_time not in raw_events:
        return False
    return bool(requested_date or requested_time)


def _extract_conflicts(raw_events: str, requested_date: str, requested_time: str) -> list[dict[str, str]]:
    """Return basic conflict evidence when an event appears to overlap."""
    if not _matching_event_found(raw_events, requested_date, requested_time):
        return []
    return [{"date": requested_date, "time": requested_time, "source": "calendar_events"}]


def _build_agreement(
    contact: dict[str, str | bool],
    requested_date: str,
    requested_time: str,
    haystack: str,
    calendar_context: dict[str, Any],
) -> dict[str, Any]:
    """Build the explicit meeting-agreement criteria from the design document."""
    participant_found = bool(contact.get("resolved"))
    exact_date_found = bool(requested_date)
    exact_time_found = bool(requested_time)
    meeting_intent_found = _contains_any(
        haystack,
        ("meeting", "meet", "call", "chat", "coffee chat", "interview", "appointment", "sync", "catch up"),
    )
    acceptance_found = _contains_any(
        haystack,
        (
            "yes",
            "works for me",
            "that works",
            "confirmed",
            "see you then",
            "let's do",
            "i can do",
            "that time is fine",
            "sounds good",
            "可以",
            "没问题",
            "确认",
            "就这个时间",
            "到时候见",
        ),
    )
    reschedule_found = _contains_any(
        haystack,
        (
            "can we reschedule",
            "need to cancel",
            "no longer works",
            "can we move",
            "can't make it",
            "cannot make it",
            "postpone",
            "改时间",
            "取消",
            "推迟",
            "换个时间",
            "我来不了",
            "重新约",
        ),
    )
    ready = all(
        (
            participant_found,
            exact_date_found,
            exact_time_found,
            meeting_intent_found,
            acceptance_found,
            not reschedule_found,
        )
    )
    return {
        "participant_found": participant_found,
        "exact_date_found": exact_date_found,
        "exact_time_found": exact_time_found,
        "meeting_intent_found": meeting_intent_found,
        "acceptance_found": acceptance_found,
        "later_cancellation_or_reschedule_found": reschedule_found,
        "ready_to_create_calendar_event": ready and not calendar_context.get("matching_event_found", False),
        "confidence": "high" if ready else "medium" if participant_found and meeting_intent_found else "low",
    }


def _contains_any(text: str, signals: tuple[str, ...]) -> bool:
    """Return whether any signal appears in text."""
    return any(signal in text for signal in signals)


def _derive_status_and_action(
    agreement: dict[str, Any],
    calendar_context: dict[str, Any],
    wants_draft: bool,
) -> tuple[str, str]:
    """Derive meeting status and calendar action from agreement/calendar facts."""
    if calendar_context.get("matching_event_found"):
        return "calendar_confirmed", "already_exists"
    if agreement["later_cancellation_or_reschedule_found"]:
        return "reschedule_requested", "do_not_create_yet"
    if agreement["ready_to_create_calendar_event"]:
        return "email_confirmed", "ready_to_create"
    if wants_draft:
        return "draft_needed", "do_not_create_yet"
    if agreement["participant_found"] and agreement["meeting_intent_found"]:
        return "proposed", "do_not_create_yet"
    return "needs_more_context", "do_not_create_yet"


def _missing_requirements(agreement: dict[str, Any]) -> list[str]:
    """Explain what prevents the meeting from being ready for calendar creation."""
    missing = []
    mapping = {
        "participant_found": "participant",
        "exact_date_found": "exact_date",
        "exact_time_found": "exact_time",
        "meeting_intent_found": "meeting_intent",
        "acceptance_found": "acceptance",
    }
    for key, label in mapping.items():
        if not agreement.get(key):
            missing.append(label)
    if agreement.get("later_cancellation_or_reschedule_found"):
        missing.append("reschedule_or_cancellation_present")
    return missing


def _extract_evidence(raw_emails: str, haystack: str) -> list[dict[str, str]]:
    """Return brief proposal/acceptance/reschedule evidence for the agent."""
    evidence: list[dict[str, str]] = []
    if _contains_any(haystack, ("would you", "available", "let's meet", "meeting", "schedule")):
        evidence.append({"type": "proposal", "text": _first_relevant_line(raw_emails, ("available", "meeting", "schedule"))})
    if _contains_any(haystack, ("works for me", "confirmed", "sounds good", "yes", "可以", "没问题")):
        evidence.append({"type": "acceptance", "text": _first_relevant_line(raw_emails, ("works", "confirmed", "yes", "可以"))})
    if _contains_any(haystack, ("reschedule", "cancel", "postpone", "改时间", "取消")):
        evidence.append({"type": "reschedule_or_cancellation", "text": _first_relevant_line(raw_emails, ("reschedule", "cancel", "postpone", "改时间", "取消"))})
    return evidence


def _first_relevant_line(raw: str, signals: tuple[str, ...]) -> str:
    """Find the first provider-output line containing one of the given signals."""
    for line in raw.splitlines():
        lowered = line.lower()
        if any(signal.lower() in lowered for signal in signals):
            return line.strip()
    return ""


def _summarize_thread(email_items: list[dict[str, Any]]) -> str:
    """Create a short deterministic summary of related email search results."""
    if not email_items:
        return "No related emails were found."
    subjects = [item["subject"] for item in email_items[:3] if item.get("subject")]
    if subjects:
        return f"Related emails include: {', '.join(subjects)}."
    return f"{len(email_items)} related email(s) found."


def _recommended_action(status: str, calendar_action: str, requested_date: str, requested_time: str) -> str:
    """Suggest the next safe action from the structured meeting status."""
    when = " ".join(part for part in (requested_date, requested_time) if part)
    if calendar_action == "ready_to_create":
        return f"Ask the user to confirm creating the calendar event for {when}."
    if status == "calendar_confirmed":
        return "Explain that a matching calendar event already exists."
    if status == "draft_needed":
        return f"Draft a scheduling reply for {when} without sending it."
    if status == "reschedule_requested":
        return "Do not create a calendar event; ask or draft a reply to resolve the new time."
    if status == "proposed":
        return "Recommend available slots or draft a reply asking for confirmation."
    return "Ask for the missing meeting details before preparing calendar actions."


def _load_context(meeting_context_json: str) -> tuple[dict[str, Any], str]:
    """Parse meeting context JSON passed back by the agent."""
    if not meeting_context_json.strip():
        return {}, "Missing meeting_context_json."
    try:
        context = json.loads(meeting_context_json)
    except json.JSONDecodeError as exc:
        return {}, f"Invalid meeting_context_json: {exc}"
    if not isinstance(context, dict):
        return {}, "meeting_context_json must decode to an object."
    return context, ""


def _validate_ready_to_create(context: dict[str, Any]) -> str:
    """Validate that the context is safe to turn into a calendar event."""
    if context.get("intent") != "meeting_schedule":
        return "Context intent is not meeting_schedule."
    if context.get("calendar_action") != "ready_to_create":
        return f"Calendar action is {context.get('calendar_action')!r}, not 'ready_to_create'."

    agreement = context.get("agreement", {})
    if not isinstance(agreement, dict):
        return "Context is missing agreement details."
    if not agreement.get("ready_to_create_calendar_event"):
        return "Meeting agreement is not ready to create a calendar event."

    request = context.get("request", {})
    contact = context.get("contact", {})
    required = {
        "participant": bool(contact.get("email") or contact.get("name")),
        "requested_date": bool(request.get("requested_date")),
        "requested_time": bool(request.get("requested_time")),
        "acceptance": bool(agreement.get("acceptance_found")),
        "meeting_intent": bool(agreement.get("meeting_intent_found")),
    }
    missing = [name for name, present in required.items() if not present]
    if missing:
        return "Missing required meeting details: " + ", ".join(missing)
    if agreement.get("later_cancellation_or_reschedule_found"):
        return "A later cancellation or reschedule signal is present."
    return ""


def _join_start_time(requested_date: str, requested_time: str) -> str:
    """Join normalized date and time into the provider's expected format."""
    return f"{requested_date} {requested_time}".strip()


def _calculate_end_time(start_time: str, duration_minutes: int) -> str:
    """Calculate meeting end time from a start time and duration."""
    try:
        start_dt = datetime.strptime(start_time, "%Y-%m-%d %H:%M")
    except ValueError:
        return ""
    return (start_dt + timedelta(minutes=duration_minutes)).strftime("%Y-%m-%d %H:%M")


def _default_meeting_title(contact: dict[str, Any], context: dict[str, Any]) -> str:
    """Generate a conservative calendar event title."""
    name = str(contact.get("name") or contact.get("email") or "Participant")
    latest_subject = str(context.get("thread_context", {}).get("latest_subject") or "")
    if latest_subject:
        return latest_subject
    return f"Meeting with {name}"


def _meeting_description(context: dict[str, Any]) -> str:
    """Build a calendar event description from meeting context evidence."""
    lines = ["Created from email-agent meeting context."]
    summary = context.get("thread_context", {}).get("summary")
    if summary:
        lines.append(f"Thread summary: {summary}")
    evidence = context.get("evidence", [])
    if evidence:
        lines.append("Evidence:")
        for item in evidence[:5]:
            text = item.get("text", "")
            if text:
                lines.append(f"- {item.get('type', 'evidence')}: {text}")
    return "\n".join(lines)


def _context_summary(context: dict[str, Any]) -> dict[str, Any]:
    """Return compact context details for write-action results."""
    return {
        "contact": context.get("contact", {}),
        "request": context.get("request", {}),
        "status": context.get("status", ""),
        "calendar_action": context.get("calendar_action", ""),
        "missing_requirements": context.get("missing_requirements", []),
    }


def _write_result(
    status: str,
    calendar_action: str,
    title: str = "",
    start_time: str = "",
    end_time: str = "",
    attendees: str = "",
    raw_result: str = "",
    error: str = "",
    context_summary: dict[str, Any] | None = None,
) -> str:
    """Serialize the result of a calendar write wrapper."""
    result = {
        "status": status,
        "calendar_action": calendar_action,
        "title": title,
        "start_time": start_time,
        "end_time": end_time,
        "attendees": attendees,
        "raw_result": raw_result,
        "error": error,
        "context_summary": context_summary or {},
    }
    return _to_json(result)


def _to_json(data: dict[str, Any]) -> str:
    """Serialize the structured meeting context result for the agent."""
    return json.dumps(data, ensure_ascii=False, indent=2)
