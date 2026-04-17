"""Urgent email detection tool.

This module ranks recent emails using deterministic urgency signals. It keeps
the workflow read-only and returns structured evidence so the agent can explain
the ranking without guessing.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from typing import Any


_email_tool: Any | None = None
_memory_tool: Any | None = None


def configure_urgency(email_tool: Any | None = None, memory_tool: Any | None = None) -> None:
    """Attach provider tools used by get_urgent_email_context."""
    global _email_tool, _memory_tool
    _email_tool = email_tool
    _memory_tool = memory_tool


def get_urgent_email_context(
    days: int = 14,
    max_emails: int = 30,
    include_unread: bool = True,
    include_unanswered: bool = True,
    mode: str = "full",
) -> str:
    """Return structured urgency context for recent emails.

    Args:
        days: Number of recent days to inspect.
        max_emails: Maximum recent emails to request from the provider.
        include_unread: Whether unread status should affect scoring.
        include_unanswered: Whether unanswered-thread status should affect scoring.
        mode: "full" for detailed ranking, "snapshot" for counts only.

    Returns:
        JSON string with urgency summary, ranked urgent emails, low-priority
        emails, ignored emails, and limitations. This tool is read-only.
    """
    days = _clamp_int(days, default=14, minimum=1, maximum=90)
    max_emails = _clamp_int(max_emails, default=30, minimum=1, maximum=200)
    mode = mode if mode in {"full", "snapshot"} else "full"
    end_date = datetime.now()
    start_date = end_date - timedelta(days=days)

    result: dict[str, Any] = {
        "intent": "urgency_query",
        "period": {
            "days": days,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
        },
        "source": {
            "recent_query": f"newer_than:{days}d",
            "max_emails": max_emails,
            "include_unread": include_unread,
            "include_unanswered": include_unanswered,
            "mode": mode,
        },
        "summary": {
            "high_count": 0,
            "medium_count": 0,
            "low_count": 0,
            "ignored_count": 0,
            "has_urgent_items": False,
            "top_categories": [],
        },
        "urgent_emails": [],
        "low_priority": [],
        "ignored_emails": [],
        "limitations": [
            "This tool ranks urgency from available metadata and previews.",
            "This tool is read-only and does not modify email state.",
        ],
    }

    if _email_tool is None:
        result["limitations"].append("No email provider tool is configured.")
        return _to_json(result)

    raw_recent = _safe_call(
        lambda: _email_tool.search_emails(query=f"newer_than:{days}d", max_results=max_emails),
        fallback="",
    )
    email_items = _parse_provider_email_list(raw_recent)
    unanswered_keys = _get_unanswered_keys(days=days, max_results=max_emails) if include_unanswered else set()

    scored = [
        _score_email(item, include_unread=include_unread, unanswered_keys=unanswered_keys)
        for item in email_items
    ]
    scored.sort(key=lambda item: (-item["score"], _urgency_order(item["urgency"]), item["subject"]))

    urgent = [item for item in scored if item["urgency"] in {"high", "medium"}]
    low_priority = [item for item in scored if item["urgency"] == "low"]
    ignored = [item for item in scored if item["urgency"] == "ignore"]

    result["summary"] = _summary(scored)
    if mode == "snapshot":
        return _to_json(result)

    result["urgent_emails"] = urgent
    result["low_priority"] = low_priority
    result["ignored_emails"] = ignored
    return _to_json(result)


def _score_email(
    item: dict[str, Any],
    include_unread: bool,
    unanswered_keys: set[str],
) -> dict[str, Any]:
    """Score one parsed email using deterministic urgency signals."""
    sender = item.get("sender", "")
    subject = item.get("subject", "")
    preview = item.get("preview", "")
    haystack = f"{sender} {subject} {preview}".lower()
    score = 0
    evidence: list[str] = []
    categories: list[str] = []
    strong_positive = False

    def add(points: int, category: str, reason: str, strong: bool = False) -> None:
        """Add score and evidence for a matched signal."""
        nonlocal score, strong_positive
        score += points
        categories.append(category)
        evidence.append(reason)
        if strong:
            strong_positive = True

    def subtract(points: int, category: str, reason: str) -> None:
        """Subtract score and keep explanatory evidence."""
        nonlocal score
        score -= points
        categories.append(category)
        evidence.append(reason)

    if _contains(haystack, _SECURITY_SIGNALS):
        add(55, "security", "account/security risk signal detected", strong=True)
    if _contains(haystack, _BILLING_SIGNALS):
        add(45, "billing", "payment or billing failure signal detected", strong=True)
    if _contains(haystack, _EXPLICIT_URGENCY_SIGNALS):
        add(40, "deadline", "explicit urgency or action-required signal detected", strong=True)
    if _contains(haystack, _SOON_DEADLINE_SIGNALS):
        add(35, "deadline", "same-day or near-term deadline signal detected", strong=True)
    if _contains(haystack, _MEETING_SIGNALS):
        add(30, "meeting", "meeting confirmation, reminder, or reschedule signal detected", strong=True)

    if include_unread and item.get("unread"):
        add(15, "unread", "email is unread")

    if _is_unanswered(item, unanswered_keys):
        add(20, "follow_up", "thread appears unanswered")

    if _looks_like_real_person(sender):
        add(15, "person", "sender looks like a real person")

    if _contains(haystack, _APPLICATION_SIGNALS):
        add(15, "application", "application, resume, job, or opportunity signal detected")

    if _contains(haystack, _DIRECT_ASK_SIGNALS) or "?" in f"{subject} {preview}":
        add(20, "follow_up", "direct ask or question detected")

    promotional = _contains(haystack, _PROMOTION_SIGNALS)
    newsletter = _contains(haystack, _NEWSLETTER_SIGNALS)
    automated = _looks_automated(sender)
    one_time_code = _contains(haystack, _ONE_TIME_CODE_SIGNALS)
    info_only = _contains(haystack, _INFO_ONLY_SIGNALS)

    if promotional:
        subtract(35, "promotion", "promotional or marketing language detected")
    if newsletter:
        subtract(30, "newsletter", "newsletter or digest language detected")
    if automated and not strong_positive:
        subtract(20, "automated", "automated sender without strong urgency signal")
    if one_time_code and not _contains(haystack, _SECURITY_SIGNALS):
        subtract(25, "verification", "one-time code without account-risk language")
    if info_only and not strong_positive:
        subtract(15, "general", "receipt, shipping, or info-only language detected")

    score = max(0, score)
    urgency = _label(score)
    category = _select_category(categories)

    if strong_positive and urgency == "ignore":
        urgency = "low"
    if promotional and not strong_positive and score < 40:
        urgency = "ignore" if score < 15 else "low"
    if one_time_code and _contains(haystack, _SECURITY_SIGNALS):
        urgency = "high"
        score = max(score, 70)
        category = "security"
        evidence.append("verification code is combined with account-risk language")

    return {
        "sender": sender,
        "subject": subject,
        "email_id": item.get("id", ""),
        "date": item.get("date", ""),
        "urgency": urgency,
        "score": score,
        "category": category,
        "confidence": _confidence(item, evidence, strong_positive),
        "evidence": evidence or ["no strong urgency signal detected"],
        "suggested_action": _suggested_action(category, urgency),
    }


_SECURITY_SIGNALS = (
    "security alert",
    "new login",
    "unauthorized",
    "unauthorised",
    "password changed",
    "suspicious activity",
    "not you",
    "account access",
    "verify your account",
)
_BILLING_SIGNALS = (
    "payment failed",
    "invoice overdue",
    "billing issue",
    "charge failed",
    "overdue",
    "refund",
)
_EXPLICIT_URGENCY_SIGNALS = (
    "urgent",
    "asap",
    "immediately",
    "deadline",
    "action required",
    "needs attention",
)
_SOON_DEADLINE_SIGNALS = (
    "today",
    "tomorrow",
    "by eod",
    "before 5 pm",
    "before 5pm",
)
_MEETING_SIGNALS = (
    "meeting",
    "reschedule",
    "confirm a meeting",
    "meeting reminder",
    "calendar conflict",
    "coffee chat",
)
_APPLICATION_SIGNALS = (
    "application",
    "resume",
    "cv",
    "job",
    "candidate",
    "opportunity",
    "interview",
)
_DIRECT_ASK_SIGNALS = (
    "can you",
    "could you",
    "please confirm",
    "please review",
    "let me know",
    "would you",
)
_PROMOTION_SIGNALS = (
    "sale",
    "discount",
    "offer",
    "rewards",
    "points",
    "promotion",
    "promo",
    "make your move",
)
_NEWSLETTER_SIGNALS = (
    "newsletter",
    "digest",
    "weekly update",
    "unsubscribe",
)
_ONE_TIME_CODE_SIGNALS = (
    "one-time code",
    "one time code",
    "verification code",
    "your code",
)
_INFO_ONLY_SIGNALS = (
    "receipt",
    "shipped",
    "delivered",
    "order confirmation",
    "fyi",
)


def _parse_provider_email_list(raw: str) -> list[dict[str, Any]]:
    """Parse provider search results into lightweight email records."""
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


def _get_unanswered_keys(days: int, max_results: int) -> set[str]:
    """Fetch unanswered context and return sender/subject/thread keys."""
    if _email_tool is None or not hasattr(_email_tool, "get_unanswered_emails"):
        return set()

    def call_within_days() -> str:
        """Try the newer within_days parameter name first."""
        return _email_tool.get_unanswered_emails(within_days=days, max_results=max_results)

    raw = _safe_call(call_within_days, fallback="")
    if raw.startswith("Error:"):
        raw = _safe_call(
            lambda: _email_tool.get_unanswered_emails(older_than_days=days, max_results=max_results),
            fallback="",
        )

    keys: set[str] = set()
    for item in _parse_provider_email_list(raw):
        keys.update(_keys_for_item(item))
    for line in raw.splitlines():
        sender_match = re.search(r"From:\s*(.+)", line)
        subject_match = re.search(r"Subject:\s*(.+)", line)
        thread_match = re.search(r"Thread ID:\s*(.+)", line)
        if sender_match:
            keys.add(_normalize_key(sender_match.group(1)))
        if subject_match:
            keys.add(_normalize_key(subject_match.group(1)))
        if thread_match:
            keys.add(_normalize_key(thread_match.group(1)))
    return {key for key in keys if key}


def _is_unanswered(item: dict[str, Any], unanswered_keys: set[str]) -> bool:
    """Check whether a parsed email matches unanswered context."""
    if not unanswered_keys:
        return False
    return any(key in unanswered_keys for key in _keys_for_item(item))


def _keys_for_item(item: dict[str, Any]) -> set[str]:
    """Build normalized matching keys for an email item."""
    keys = {
        _normalize_key(item.get("sender", "")),
        _normalize_key(item.get("subject", "")),
        _normalize_key(item.get("id", "")),
    }
    return {key for key in keys if key}


def _normalize_key(value: str) -> str:
    """Normalize a matching key."""
    return re.sub(r"\s+", " ", str(value).strip().lower())


def _contains(text: str, signals: tuple[str, ...]) -> bool:
    """Return whether any signal appears in text."""
    return any(signal in text for signal in signals)


def _looks_like_real_person(sender: str) -> bool:
    """Heuristically detect non-automated human senders."""
    lowered = sender.lower()
    if _looks_automated(sender):
        return False
    if any(domain in lowered for domain in ("gmail.com", "qq.com", "outlook.com", "hotmail.com")):
        return True
    return bool(re.match(r"[^<@]+<[^>]+>", sender)) and not any(term in lowered for term in ("team", "support", "help"))


def _looks_automated(sender: str) -> bool:
    """Heuristically detect automated senders."""
    lowered = sender.lower()
    return any(term in lowered for term in ("noreply@", "no-reply@", "notifications@", "notification@", "marketing@", "newsletter"))


def _select_category(categories: list[str]) -> str:
    """Choose one main category from matched signals."""
    order = [
        "security",
        "billing",
        "deadline",
        "meeting",
        "follow_up",
        "application",
        "promotion",
        "newsletter",
        "verification",
        "person",
        "unread",
        "automated",
        "general",
    ]
    for category in order:
        if category in categories:
            return category
    return "general"


def _label(score: int) -> str:
    """Convert score into urgency label."""
    if score >= 70:
        return "high"
    if score >= 40:
        return "medium"
    if score >= 15:
        return "low"
    return "ignore"


def _urgency_order(label: str) -> int:
    """Sort labels from highest to lowest urgency."""
    return {"high": 0, "medium": 1, "low": 2, "ignore": 3}.get(label, 9)


def _confidence(item: dict[str, Any], evidence: list[str], strong_positive: bool) -> str:
    """Return a simple confidence label."""
    subject = item.get("subject", "").lower()
    if strong_positive and any(signal in subject for signal in _SECURITY_SIGNALS + _BILLING_SIGNALS + _EXPLICIT_URGENCY_SIGNALS):
        return "high"
    if evidence:
        return "medium"
    return "low"


def _suggested_action(category: str, urgency: str) -> str:
    """Suggest a next action for the urgency item."""
    if category == "security":
        return "Review account activity."
    if category == "billing":
        return "Review the payment or billing issue."
    if category == "deadline":
        return "Review and respond before the deadline."
    if category == "meeting":
        return "Confirm, reschedule, or review the meeting details."
    if category == "follow_up":
        return "Reply or follow up if the conversation is still active."
    if category == "application":
        return "Review the application or opportunity details."
    if urgency == "ignore":
        return "No immediate action needed."
    return "Review when convenient."


def _summary(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """Build aggregate counts and top categories."""
    counts = {
        "high_count": sum(1 for item in scored if item["urgency"] == "high"),
        "medium_count": sum(1 for item in scored if item["urgency"] == "medium"),
        "low_count": sum(1 for item in scored if item["urgency"] == "low"),
        "ignored_count": sum(1 for item in scored if item["urgency"] == "ignore"),
    }
    category_counts: dict[str, int] = {}
    for item in scored:
        if item["urgency"] in {"high", "medium"}:
            category_counts[item["category"]] = category_counts.get(item["category"], 0) + 1
    top_categories = sorted(category_counts, key=lambda category: (-category_counts[category], category))[:3]
    return {
        **counts,
        "has_urgent_items": counts["high_count"] > 0 or counts["medium_count"] > 0,
        "top_categories": top_categories,
    }


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
    """Serialize the structured urgency result for the agent."""
    return json.dumps(data, ensure_ascii=False, indent=2)
