from __future__ import annotations

import re
from typing import Any, Callable


SEARCH_MAX_RESULTS = 350
MAX_LOOKBACK_DAYS = 7
UNANSWERED_WITHIN_DAYS = 7
UNANSWERED_MAX_RESULTS = 30
UNANSWERED_LOOKUP_LIMIT = 10
EMAIL_ID_PATTERN = re.compile(r"^\s*ID:\s*(\S+)\s*$", re.MULTILINE)
FROM_LINE_PATTERN = re.compile(r"^\d+\.\s+From:\s+(.+)$")
URGENT_QUERY_TERMS = (
    "urgent",
    "asap",
    "immediately",
    "important",
    "critical",
    "priority",
    "attention",
    '"high priority"',
    '"needs attention"',
    '"for your attention"',
    '"attention required"',
    '"requires attention"',
    '"action required"',
    '"immediate action"',
    '"response needed"',
    '"please respond"',
    '"for your review"',
    '"review needed"',
    '"time sensitive"',
    '"urgent response"',
    "deadline",
    "overdue",
    "reminder",
    '"final notice"',
    "alert",
    '"security alert"',
)


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:urgent_email_triage] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:urgent_email_triage] finished {name}", flush=True)
    return name, kwargs, text


def _build_urgent_query(days: int) -> str:
    return f"in:inbox newer_than:{days}d ({' OR '.join(URGENT_QUERY_TERMS)})"


def _extract_email_ids(search_output: str) -> list[str]:
    matched_ids: list[str] = []
    seen_ids: set[str] = set()
    for raw_email_id in EMAIL_ID_PATTERN.findall(str(search_output or "")):
        email_id = raw_email_id.strip()
        if not email_id or email_id in seen_ids:
            continue
        seen_ids.add(email_id)
        matched_ids.append(email_id)
    return matched_ids


def _extract_email_address(raw_from: str) -> str:
    value = str(raw_from or "").strip()
    email_match = re.search(r"<([^>]+)>", value)
    if email_match:
        return email_match.group(1).strip()
    return value


def _extract_unanswered_entries(unanswered_output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in str(unanswered_output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        from_match = FROM_LINE_PATTERN.match(line)
        if from_match:
            if current and current.get("from") and current.get("subject"):
                entries.append(current)
            raw_from = from_match.group(1).strip()
            current = {
                "from": raw_from,
                "from_email": _extract_email_address(raw_from),
                "subject": "",
                "thread_id": "",
            }
            continue

        if current is None:
            continue

        if line.startswith("Subject:"):
            current["subject"] = line.removeprefix("Subject:").strip()
        elif line.startswith("Thread ID:"):
            current["thread_id"] = line.removeprefix("Thread ID:").strip()

    if current and current.get("from") and current.get("subject"):
        entries.append(current)

    return entries


def _escape_query_value(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"').strip()


def _build_unanswered_lookup_query(*, days: int, from_email: str, subject: str) -> str:
    escaped_subject = _escape_query_value(subject)
    return f'in:inbox newer_than:{days}d from:{from_email} subject:"{escaped_subject}"'


def execute_skill(*, arguments, used_tools, skill_spec):
    raw_days = arguments.get("days", 7)
    days = int(raw_days)
    if days < 1:
        days = 1
    if days > MAX_LOOKBACK_DAYS:
        days = MAX_LOOKBACK_DAYS

    search_query = _build_urgent_query(days)
    print(f"[skill:urgent_email_triage] start days={days}", flush=True)

    _, search_kwargs, search_text = _call_tool(
        "search_emails",
        used_tools["search_emails"],
        {"query": search_query, "max_results": SEARCH_MAX_RESULTS},
    )
    _, unanswered_kwargs, unanswered_text = _call_tool(
        "get_unanswered_emails",
        used_tools["get_unanswered_emails"],
        {"within_days": UNANSWERED_WITHIN_DAYS, "max_results": UNANSWERED_MAX_RESULTS},
    )

    matched_email_ids = _extract_email_ids(search_text)
    body_results: list[dict[str, Any]] = []
    for email_id in matched_email_ids:
        _, body_kwargs, body_text = _call_tool(
            "get_email_body",
            used_tools["get_email_body"],
            {"email_id": email_id},
        )
        body_results.append(
            {
                "email_id": email_id,
                "kwargs": body_kwargs,
                "text": body_text,
            }
        )

    unanswered_entries = _extract_unanswered_entries(unanswered_text)[:UNANSWERED_LOOKUP_LIMIT]
    unanswered_lookup_results: list[dict[str, Any]] = []
    unanswered_body_results: list[dict[str, Any]] = []
    for entry in unanswered_entries:
        lookup_query = _build_unanswered_lookup_query(
            days=days,
            from_email=entry["from_email"],
            subject=entry["subject"],
        )
        _, lookup_kwargs, lookup_text = _call_tool(
            "search_emails",
            used_tools["search_emails"],
            {"query": lookup_query, "max_results": 1},
        )
        lookup_ids = _extract_email_ids(lookup_text)
        selected_email_id = lookup_ids[0] if lookup_ids else ""
        unanswered_lookup_results.append(
            {
                "entry": entry,
                "kwargs": lookup_kwargs,
                "text": lookup_text,
                "matched_email_id": selected_email_id,
            }
        )
        if not selected_email_id:
            continue

        _, body_kwargs, body_text = _call_tool(
            "get_email_body",
            used_tools["get_email_body"],
            {"email_id": selected_email_id},
        )
        unanswered_body_results.append(
            {
                "entry": entry,
                "email_id": selected_email_id,
                "kwargs": body_kwargs,
                "text": body_text,
            }
        )

    print(
        "[skill:urgent_email_triage] collected "
        f"search_matches={len(matched_email_ids)} "
        f"body_fetches={len(body_results)} "
        f"unanswered_entries={len(unanswered_entries)} "
        f"unanswered_body_fetches={len(unanswered_body_results)}",
        flush=True,
    )

    lines = [
        "[URGENT_EMAIL_TRIAGE_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'urgent_email_triage')}",
        f"days: {days}",
        f"search_query: {search_query}",
        f"urgent_keywords: {', '.join(URGENT_QUERY_TERMS)}",
        f"max_lookback_days: {MAX_LOOKBACK_DAYS}",
        f"search_max_results: {SEARCH_MAX_RESULTS}",
        f"unanswered_within_days: {UNANSWERED_WITHIN_DAYS}",
        f"unanswered_max_results: {UNANSWERED_MAX_RESULTS}",
        f"unanswered_lookup_limit: {UNANSWERED_LOOKUP_LIMIT}",
        f"matched_email_count: {len(matched_email_ids)}",
        f"body_fetch_count: {len(body_results)}",
        f"unanswered_entry_count: {len(unanswered_entries)}",
        f"unanswered_body_fetch_count: {len(unanswered_body_results)}",
        "notes:",
        "- The lookback window is capped at 7 days.",
        "- search_emails scans the inbox for urgent, attention, and high-priority English keywords within the recent time window.",
        "- get_unanswered_emails adds unreplied human-thread context from the same capped time window.",
        "- Because get_unanswered_emails returns thread ids instead of message ids, the skill runs fixed lookup searches to recover a message id before calling get_email_body.",
        "- get_email_body is fetched for every matched urgent email id returned by the search results and for unanswered emails that can be mapped back to a message id.",
        "- The sections below are raw tool outputs for the finalizer LLM to summarize without adding new facts.",
        "",
        "[SEARCH_EMAILS]",
        "tool: search_emails",
        f"arguments: {search_kwargs}",
        search_text,
        "",
        "[GET_UNANSWERED_EMAILS]",
        "tool: get_unanswered_emails",
        f"arguments: {unanswered_kwargs}",
        unanswered_text,
        "",
        "[MATCHED_URGENT_EMAIL_IDS]",
        ", ".join(matched_email_ids) if matched_email_ids else "(none)",
        "",
        "[EMAIL_BODY_RESULTS]",
        f"count: {len(body_results)}",
    ]

    if not body_results:
        lines.append("(no matched urgent email ids were available for get_email_body)")
    else:
        for index, body_result in enumerate(body_results, start=1):
            lines.extend(
                [
                    "",
                    f"[EMAIL_BODY_{index}]",
                    "tool: get_email_body",
                    f"arguments: {body_result['kwargs']}",
                    body_result["text"],
                ]
            )

    lines.extend(
        [
            "",
            "[UNANSWERED_EMAIL_ID_LOOKUPS]",
            f"count: {len(unanswered_lookup_results)}",
        ]
    )

    if not unanswered_lookup_results:
        lines.append("(no unanswered entries were available for lookup)")
    else:
        for index, lookup_result in enumerate(unanswered_lookup_results, start=1):
            entry = lookup_result["entry"]
            lines.extend(
                [
                    "",
                    f"[UNANSWERED_LOOKUP_{index}]",
                    f"from: {entry['from']}",
                    f"subject: {entry['subject']}",
                    f"thread_id: {entry.get('thread_id', '') or '(none)'}",
                    "tool: search_emails",
                    f"arguments: {lookup_result['kwargs']}",
                    lookup_result["text"],
                    f"matched_email_id: {lookup_result['matched_email_id'] or '(none)'}",
                ]
            )

    lines.extend(
        [
            "",
            "[UNANSWERED_EMAIL_BODY_RESULTS]",
            f"count: {len(unanswered_body_results)}",
        ]
    )

    if not unanswered_body_results:
        lines.append("(no unanswered email ids were available for get_email_body)")
    else:
        for index, body_result in enumerate(unanswered_body_results, start=1):
            entry = body_result["entry"]
            lines.extend(
                [
                    "",
                    f"[UNANSWERED_EMAIL_BODY_{index}]",
                    f"from: {entry['from']}",
                    f"subject: {entry['subject']}",
                    "tool: get_email_body",
                    f"arguments: {body_result['kwargs']}",
                    body_result["text"],
                ]
            )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": (
            f"Collected urgent-email triage data from keyword search, unanswered-thread context, "
            f"lookup searches for unanswered message ids, and full bodies within the last {days} day(s)."
        ),
    }
