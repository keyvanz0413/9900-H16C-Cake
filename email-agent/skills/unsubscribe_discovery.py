from __future__ import annotations

import hashlib
import json
import re
from email.utils import parseaddr
from typing import Any, Callable


DEFAULT_DAYS = 30
MAX_DAYS = 90
DEFAULT_MAX_RESULTS = 100
MAX_RESULTS_CAP = 250
EMAIL_ID_PATTERN = re.compile(r"^\s*ID:\s*(\S+)\s*$", re.MULTILINE)
SEARCH_RESULT_FROM_PATTERN = re.compile(r"^(?:\d+\.\s+)?(?:\[[^\]]+\]\s+)*From:\s*(.+)$")
METHOD_PRIORITY = {
    "one_click": 0,
    "mailto": 1,
    "website": 2,
    "unknown": 3,
}


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:unsubscribe_discovery] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:unsubscribe_discovery] finished {name}", flush=True)
    return name, kwargs, text


def _loads_mapping(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(raw_text or "").strip())
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def _extract_email_ids(search_output: str) -> list[str]:
    email_ids: list[str] = []
    seen: set[str] = set()
    for raw_email_id in EMAIL_ID_PATTERN.findall(str(search_output or "")):
        email_id = raw_email_id.strip()
        if not email_id or email_id in seen:
            continue
        seen.add(email_id)
        email_ids.append(email_id)
    return email_ids


def _extract_search_entries(search_output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in str(search_output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        from_match = SEARCH_RESULT_FROM_PATTERN.match(line)
        if from_match:
            if current and current.get("email_id"):
                entries.append(current)
            current = {"from": from_match.group(1).strip()}
            continue

        if current is None:
            continue

        if line.startswith("Subject:"):
            current["subject"] = line.split("Subject:", 1)[1].strip()
            continue

        if line.startswith("Date:"):
            current["date"] = line.split("Date:", 1)[1].strip()
            continue

        if line.startswith("ID:"):
            current["email_id"] = line.split("ID:", 1)[1].strip()

    if current and current.get("email_id"):
        entries.append(current)

    if entries:
        return entries

    return [
        {
            "from": "(unknown sender)",
            "subject": "(no subject)",
            "email_id": email_id,
        }
        for email_id in _extract_email_ids(search_output)
    ]


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if number < minimum:
        return minimum
    if number > maximum:
        return maximum
    return number


def _build_search_query(days: int) -> str:
    return (
        f'in:inbox newer_than:{days}d '
        '(unsubscribe OR newsletter OR subscription OR "manage preferences" OR "email preferences" OR marketing)'
    )


def _sender_parts(raw_from: str) -> tuple[str, str, str]:
    display_name, email_address = parseaddr(str(raw_from or "").strip())
    sender_email = email_address.strip().lower()
    sender_domain = sender_email.rsplit("@", 1)[-1] if "@" in sender_email else ""
    sender = str(raw_from or "").strip() or sender_email or "(unknown sender)"
    if not sender and display_name:
        sender = display_name
    return sender, sender_email, sender_domain


def _candidate_id(*, sender_email: str, sender_domain: str) -> str:
    stable_source = "|".join([sender_email, sender_domain]).strip("|") or "unknown"
    digest = hashlib.sha1(stable_source.encode("utf-8")).hexdigest()[:12]
    readable = sender_email or sender_domain or "unknown"
    readable = re.sub(r"[^a-zA-Z0-9_.@-]+", "-", readable).strip("-")[:48] or "unknown"
    return f"{readable}:{digest}"


def _risk_level(method: str) -> str:
    if method == "one_click":
        return "low"
    if method == "mailto":
        return "medium"
    if method == "website":
        return "medium"
    if method == "multiple":
        return "review"
    return "unknown"


def _best_method(existing: str, incoming: str) -> str:
    existing_priority = METHOD_PRIORITY.get(existing, METHOD_PRIORITY["unknown"])
    incoming_priority = METHOD_PRIORITY.get(incoming, METHOD_PRIORITY["unknown"])
    return incoming if incoming_priority < existing_priority else existing


def _normalize_method(raw_method: Any) -> str:
    method = str(raw_method or "unknown").strip().lower()
    return method or "unknown"


def _build_evidence(unsubscribe: dict[str, Any], item_error: str) -> list[str]:
    options = unsubscribe.get("options") if isinstance(unsubscribe.get("options"), dict) else {}
    evidence: list[str] = []
    if "one_click" in options:
        evidence.append("One-click unsubscribe is available.")
    if "mailto" in options:
        evidence.append("A mailto unsubscribe request can be sent.")
    website_option = options.get("website") if isinstance(options.get("website"), dict) else {}
    if website_option.get("url"):
        evidence.append("A header-based unsubscribe webpage is available.")
    manual_links = website_option.get("manual_links")
    if isinstance(manual_links, list) and manual_links:
        evidence.append("Manual unsubscribe links were found in the email content.")
    if item_error:
        evidence.append(f"Tool warning: {item_error}")
    if not evidence:
        evidence.append("No actionable unsubscribe option was found.")
    return evidence


def _merge_candidate(candidates: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> None:
    key = candidate["candidate_id"]
    existing = candidates.get(key)
    if existing is None:
        candidates[key] = candidate
        return

    existing["recent_count"] += 1
    for subject in candidate.get("subjects", []):
        if subject and subject not in existing["subjects"] and len(existing["subjects"]) < 5:
            existing["subjects"].append(subject)
    for email_id in candidate.get("sample_email_ids", []):
        if email_id and email_id not in existing["sample_email_ids"] and len(existing["sample_email_ids"]) < 5:
            existing["sample_email_ids"].append(email_id)

    chosen_method = _best_method(existing.get("method", "unknown"), candidate.get("method", "unknown"))
    if chosen_method != existing.get("method"):
        existing["method"] = chosen_method
        existing["risk_level"] = _risk_level(chosen_method)
        existing["representative_email_id"] = candidate["representative_email_id"]
        existing["unsubscribe"] = candidate["unsubscribe"]
        existing["evidence"] = candidate["evidence"]


def execute_skill(*, arguments, used_tools, skill_spec):
    days = _clamp_int(arguments.get("days", DEFAULT_DAYS), default=DEFAULT_DAYS, minimum=1, maximum=MAX_DAYS)
    max_results = _clamp_int(
        arguments.get("max_results", DEFAULT_MAX_RESULTS),
        default=DEFAULT_MAX_RESULTS,
        minimum=1,
        maximum=MAX_RESULTS_CAP,
    )
    search_query = _build_search_query(days)

    print(
        f"[skill:unsubscribe_discovery] start days={days} max_results={max_results}",
        flush=True,
    )

    _, search_kwargs, search_text = _call_tool(
        "search_emails",
        used_tools["search_emails"],
        {"query": search_query, "max_results": max_results},
    )
    search_entries = _extract_search_entries(search_text)
    email_ids = [entry["email_id"] for entry in search_entries if entry.get("email_id")]
    if not email_ids:
        email_ids = _extract_email_ids(search_text)
        search_entries = [
            {"from": "(unknown sender)", "subject": "(no subject)", "email_id": email_id}
            for email_id in email_ids
        ]

    _, unsubscribe_kwargs, unsubscribe_text = _call_tool(
        "get_unsubscribe_info",
        used_tools["get_unsubscribe_info"],
        {"email_ids": email_ids},
    )
    unsubscribe_payload = _loads_mapping(unsubscribe_text)
    unsubscribe_items = {
        str(item.get("email_id") or "").strip(): item
        for item in unsubscribe_payload.get("items", [])
        if isinstance(item, dict) and str(item.get("email_id") or "").strip()
    }

    candidates: dict[str, dict[str, Any]] = {}
    inspected_count = 0
    unsubscribe_summary = unsubscribe_payload.get("summary") if isinstance(unsubscribe_payload.get("summary"), dict) else {}
    error_count = int(unsubscribe_summary.get("error_count", 0) or 0)

    for entry in search_entries:
        email_id = str(entry.get("email_id") or "").strip()
        item = unsubscribe_items.get(email_id, {})
        unsubscribe = item.get("unsubscribe") if isinstance(item.get("unsubscribe"), dict) else {}
        item_error = str(item.get("error") or "").strip()

        raw_from = str(entry.get("from") or "").strip()
        sender, sender_email, sender_domain = _sender_parts(raw_from)
        subject = str(entry.get("subject") or "").strip() or "(no subject)"
        method = _normalize_method(unsubscribe.get("method"))
        evidence = _build_evidence(unsubscribe, item_error)

        candidate = {
            "candidate_id": _candidate_id(sender_email=sender_email, sender_domain=sender_domain),
            "sender": sender,
            "sender_email": sender_email,
            "sender_domain": sender_domain,
            "representative_email_id": email_id,
            "sample_email_ids": [email_id],
            "recent_count": 1,
            "subjects": [subject],
            "method": method,
            "risk_level": _risk_level(method),
            "unsubscribe": unsubscribe,
            "status": "candidate",
            "evidence": evidence,
            "raw_tool_calls": {
                "get_unsubscribe_info": unsubscribe_kwargs,
            },
        }
        _merge_candidate(candidates, candidate)
        inspected_count += 1

    ordered_candidates = sorted(
        candidates.values(),
        key=lambda item: (
            METHOD_PRIORITY.get(str(item.get("method") or "unknown"), METHOD_PRIORITY["unknown"]),
            -int(item.get("recent_count") or 0),
            str(item.get("sender_email") or item.get("sender") or ""),
        ),
    )

    lines = [
        "[UNSUBSCRIBE_DISCOVERY_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'unsubscribe_discovery')}",
        f"days: {days}",
        f"max_results: {max_results}",
        f"search_query: {search_query}",
        f"matched_email_id_count: {len(email_ids)}",
        f"inspected_email_count: {inspected_count}",
        f"candidate_count: {len(ordered_candidates)}",
        f"metadata_error_count: {error_count}",
        "notes:",
        "- This is a read-only discovery result.",
        "- No unsubscribe action was executed.",
        "- No POST request, mailto message, website visit, browser automation, archive, or label action was performed.",
        "- The workflow uses get_unsubscribe_info as the single unsubscribe inspection entrypoint.",
        "- When presenting candidates, include representative_email_id so a later confirmed execution can target the exact message.",
        "",
        "[SEARCH_EMAILS]",
        f"tool: search_emails",
        f"arguments: {search_kwargs}",
        search_text,
        "",
        "[GET_UNSUBSCRIBE_INFO]",
        "tool: get_unsubscribe_info",
        f"arguments: {unsubscribe_kwargs}",
        unsubscribe_text,
        "",
        "[CANDIDATES_JSON]",
        json.dumps(ordered_candidates, ensure_ascii=False, indent=2, sort_keys=True),
    ]

    print(
        f"[skill:unsubscribe_discovery] completed inspected={inspected_count} candidates={len(ordered_candidates)}",
        flush=True,
    )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": (
            "Collected read-only unsubscribe discovery metadata and classified candidates "
            "without executing unsubscribe actions."
        ),
    }
