"""Weekly email activity aggregation tool.

This module keeps the weekly-summary workflow read-only and deterministic. The
agent can use the returned JSON as a stable fact source, then decide how to
format it for the user.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any


_email_tool: Any | None = None
_calendar_tool: Any | None = None


def configure_weekly_summary(email_tool: Any | None = None, calendar_tool: Any | None = None) -> None:
    """Attach provider tools used by get_weekly_email_activity.

    The public tool function keeps a simple schema for the agent, while this
    setup hook lets agent.py provide the active Gmail/Outlook and Calendar
    instances at startup.
    """
    global _email_tool, _calendar_tool
    _email_tool = email_tool
    _calendar_tool = calendar_tool


def get_weekly_email_activity(
    days: int = 7,
    max_emails: int = 50,
    include_calendar: bool = True,
    include_unanswered: bool = True,
) -> str:
    """Collect structured email activity for a weekly summary.

    Args:
        days: Number of recent days to inspect. Defaults to 7.
        max_emails: Maximum emails to request from the email provider.
        include_calendar: Whether to include upcoming calendar context.
        include_unanswered: Whether to include unanswered/follow-up context.

    Returns:
        JSON string with period, counts, themes, follow-up, calendar, suggested
        priorities, and limitations. This tool is read-only.
    """
    days = _clamp_int(days, default=7, minimum=1, maximum=90)
    max_emails = _clamp_int(max_emails, default=50, minimum=1, maximum=200)
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    result: dict[str, Any] = {
        "period": {
            "days": days,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        },
        "source": "get_weekly_email_activity",
        "counts": {
            "total_emails": 0,
            "unread_emails": 0,
            "senders": 0,
        },
        "themes": [],
        "unanswered": {
            "included": include_unanswered,
            "raw_result": "",
            "detected": False,
        },
        "calendar": {
            "included": include_calendar,
            "upcoming_events_found": False,
            "raw_result": "",
        },
        "suggested_priorities": [],
        "limitations": [
            "This tool summarizes provider results and does not modify email or calendar data.",
            "Calendar confirmation is separate from email-thread confirmation.",
        ],
    }

    if _email_tool is None:
        result["limitations"].append("No email provider tool is configured.")
        return _to_json(result)

    query = f"newer_than:{days}d"
    raw_emails = _safe_call(
        lambda: _email_tool.search_emails(query=query, max_results=max_emails),
        fallback="",
    )
    email_items = _parse_provider_email_list(raw_emails)

    result["query"] = query
    result["raw_email_result"] = raw_emails
    result["counts"] = {
        "total_emails": _extract_total_count(raw_emails, email_items),
        "unread_emails": sum(1 for item in email_items if item["unread"]),
        "senders": len({item["sender"] for item in email_items if item["sender"]}),
    }
    result["themes"] = _build_themes(email_items)

    if include_unanswered:
        unanswered = _get_unanswered(days=days, max_results=20)
        result["unanswered"]["raw_result"] = unanswered
        result["unanswered"]["detected"] = _looks_like_non_empty_result(unanswered)

    if include_calendar and _calendar_tool is not None:
        calendar_result = _get_calendar(days_ahead=days)
        result["calendar"]["raw_result"] = calendar_result
        result["calendar"]["upcoming_events_found"] = _looks_like_non_empty_result(calendar_result)
    elif include_calendar:
        result["limitations"].append("No calendar provider tool is configured.")

    result["suggested_priorities"] = _suggest_priorities(
        themes=result["themes"],
        unanswered_detected=result["unanswered"]["detected"],
        calendar_found=result["calendar"]["upcoming_events_found"],
    )

    return _to_json(result)


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


def _build_themes(email_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group parsed emails into weekly-summary categories."""
    category_defs = [
        (
            "Security alerts",
            "high",
            ("security", "login", "authorization", "authorisation", "account", "verify", "verification"),
        ),
        (
            "Meeting scheduling",
            "medium",
            ("meeting", "schedule", "available", "availability", "coffee chat", "tomorrow", "next week"),
        ),
        (
            "Applications / resumes",
            "medium",
            ("application", "job", "resume", "cv", "candidate", "opportunity", "internship"),
        ),
        (
            "Newsletters / promotions",
            "low",
            ("unsubscribe", "newsletter", "rewards", "points", "promotion", "promo", "offer"),
        ),
    ]
    grouped: dict[str, dict[str, Any]] = {}

    for item in email_items:
        haystack = f"{item.get('sender', '')} {item.get('subject', '')} {item.get('preview', '')}".lower()
        matched = False
        for name, importance, signals in category_defs:
            if any(signal in haystack for signal in signals):
                _add_theme_item(grouped, name, importance, item, _status_for_item(name, haystack))
                matched = True
                break
        if not matched:
            _add_theme_item(grouped, "General FYI", "low", item, "informational")

    themes = list(grouped.values())
    for theme in themes:
        theme["email_count"] = len(theme["items"])
        theme["summary"] = _theme_summary(theme["name"], theme["email_count"])

    importance_order = {"high": 0, "medium": 1, "low": 2}
    themes.sort(key=lambda theme: (importance_order.get(theme["importance"], 9), theme["name"]))
    return themes


def _add_theme_item(
    grouped: dict[str, dict[str, Any]],
    name: str,
    importance: str,
    item: dict[str, Any],
    status: str,
) -> None:
    """Add one parsed email to a category bucket."""
    theme = grouped.setdefault(
        name,
        {
            "name": name,
            "importance": importance,
            "email_count": 0,
            "summary": "",
            "items": [],
        },
    )
    theme["items"].append(
        {
            "sender": item.get("sender", ""),
            "subject": item.get("subject", ""),
            "status": "unread" if item.get("unread") else status,
            "date": item.get("date", ""),
            "reason": _reason_for_category(name),
            "email_id": item.get("id", ""),
        }
    )


def _status_for_item(category: str, haystack: str) -> str:
    """Infer an item's status, especially proposed vs email-confirmed meetings."""
    if category == "Meeting scheduling":
        if any(signal in haystack for signal in ("yes", "works for me", "confirmed", "works well")):
            return "email_confirmed"
        if any(signal in haystack for signal in ("available", "would you", "what time", "schedule")):
            return "proposed"
        return "unclear"
    return "informational"


def _reason_for_category(name: str) -> str:
    """Return the human-readable reason for why an email matched a category."""
    reasons = {
        "Security alerts": "Security or account-access language detected",
        "Meeting scheduling": "Meeting or availability language detected",
        "Applications / resumes": "Application, resume, candidate, or opportunity language detected",
        "Newsletters / promotions": "Newsletter, promotion, or unsubscribe language detected",
        "General FYI": "No stronger category signal detected",
    }
    return reasons.get(name, "Matched category signals")


def _theme_summary(name: str, count: int) -> str:
    """Create a short category summary for the structured JSON result."""
    summaries = {
        "Security alerts": f"{count} security or account-access related email(s).",
        "Meeting scheduling": f"{count} meeting or scheduling related email(s).",
        "Applications / resumes": f"{count} application, resume, or opportunity related email(s).",
        "Newsletters / promotions": f"{count} promotional or newsletter-like email(s).",
        "General FYI": f"{count} general informational email(s).",
    }
    return summaries.get(name, f"{count} email(s) in this category.")


def _get_unanswered(days: int, max_results: int) -> str:
    """Fetch unanswered/follow-up context if the provider supports it."""
    if _email_tool is None or not hasattr(_email_tool, "get_unanswered_emails"):
        return "Unanswered email tracking not available for this provider."

    def call_within_days() -> str:
        """Try the newer within_days parameter name first."""
        return _email_tool.get_unanswered_emails(within_days=days, max_results=max_results)

    result = _safe_call(call_within_days, fallback="")
    if not result.startswith("Error:"):
        return result

    def call_older_than_days() -> str:
        """Fallback for providers that still use older_than_days."""
        return _email_tool.get_unanswered_emails(older_than_days=days, max_results=max_results)

    return _safe_call(call_older_than_days, fallback=result)


def _get_calendar(days_ahead: int) -> str:
    """Fetch upcoming calendar context if the provider supports it."""
    if _calendar_tool is None:
        return "Calendar provider not available."
    if hasattr(_calendar_tool, "list_events"):
        return _safe_call(lambda: _calendar_tool.list_events(days_ahead=days_ahead), fallback="")
    if hasattr(_calendar_tool, "get_today_events"):
        return _safe_call(lambda: _calendar_tool.get_today_events(), fallback="")
    return "Calendar event listing not available for this provider."


def _looks_like_non_empty_result(raw: str) -> bool:
    """Heuristically decide whether a provider result contains real items."""
    lowered = raw.lower()
    empty_markers = (
        "not available",
        "no upcoming",
        "no events",
        "no unanswered",
        "found 0",
        "0 email",
        "none",
    )
    return bool(raw.strip()) and not any(marker in lowered for marker in empty_markers)


def _suggest_priorities(
    themes: list[dict[str, Any]],
    unanswered_detected: bool,
    calendar_found: bool,
) -> list[str]:
    """Generate high-level next-step suggestions from structured facts."""
    priorities: list[str] = []
    theme_names = {theme["name"] for theme in themes}

    if "Security alerts" in theme_names:
        priorities.append("Review security and login alerts first.")
    if unanswered_detected:
        priorities.append("Review unanswered or follow-up threads.")
    if "Meeting scheduling" in theme_names and not calendar_found:
        priorities.append("Check whether email-confirmed meetings should be added to calendar.")
    if "Applications / resumes" in theme_names:
        priorities.append("Review application or resume-related activity.")
    if "Newsletters / promotions" in theme_names:
        priorities.append("Deprioritize promotional messages unless they are personally relevant.")

    if not priorities:
        priorities.append("No obvious urgent priority detected from the weekly activity.")
    return priorities


def _to_json(data: dict[str, Any]) -> str:
    """Serialize the structured activity result for the agent."""
    return json.dumps(data, ensure_ascii=False, indent=2)
