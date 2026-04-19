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
HEADER_NAMES = [
    "From",
    "Subject",
    "Date",
    "List-Unsubscribe",
    "List-Unsubscribe-Post",
    "List-Id",
    "Precedence",
]
EMAIL_ID_PATTERN = re.compile(r"^\s*ID:\s*(\S+)\s*$", re.MULTILINE)
METHOD_PRIORITY = {
    "one_click": 0,
    "mailto": 1,
    "website": 2,
    "multiple": 3,
    "unknown": 4,
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


def _candidate_id(*, sender_email: str, sender_domain: str, list_id: str) -> str:
    stable_source = "|".join([sender_email, sender_domain, list_id]).strip("|") or "unknown"
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
    include_body_links = bool(arguments.get("include_body_links", False))
    search_query = _build_search_query(days)

    print(
        f"[skill:unsubscribe_discovery] start days={days} max_results={max_results} include_body_links={include_body_links}",
        flush=True,
    )

    _, search_kwargs, search_text = _call_tool(
        "search_emails",
        used_tools["search_emails"],
        {"query": search_query, "max_results": max_results},
    )
    email_ids = _extract_email_ids(search_text)
    candidates: dict[str, dict[str, Any]] = {}
    inspected_count = 0
    error_count = 0

    for email_id in email_ids:
        _, header_kwargs, header_text = _call_tool(
            "get_email_headers",
            used_tools["get_email_headers"],
            {"email_id": email_id, "header_names": HEADER_NAMES},
        )
        header_payload = _loads_mapping(header_text)
        headers = header_payload.get("headers") if isinstance(header_payload.get("headers"), dict) else {}
        if not header_payload.get("ok"):
            error_count += 1

        list_unsubscribe = str(headers.get("List-Unsubscribe") or "").strip()
        list_unsubscribe_post = str(headers.get("List-Unsubscribe-Post") or "").strip()

        _, parse_kwargs, parsed_text = _call_tool(
            "parse_list_unsubscribe_header",
            used_tools["parse_list_unsubscribe_header"],
            {"header_value": list_unsubscribe},
        )
        parsed_payload = _loads_mapping(parsed_text)

        _, classify_kwargs, classification_text = _call_tool(
            "classify_unsubscribe_method",
            used_tools["classify_unsubscribe_method"],
            {
                "parsed_list_unsubscribe": parsed_payload,
                "list_unsubscribe_post": list_unsubscribe_post,
            },
        )
        classification = _loads_mapping(classification_text)

        raw_from = str(headers.get("From") or "").strip()
        sender, sender_email, sender_domain = _sender_parts(raw_from)
        subject = str(headers.get("Subject") or "").strip() or "(no subject)"
        list_id = str(headers.get("List-Id") or "").strip()
        method = str(classification.get("method") or "unknown").strip() or "unknown"
        evidence = [str(item) for item in classification.get("reasons", []) if str(item).strip()]
        if list_id:
            evidence.append(f"List-Id present: {list_id}")

        candidate = {
            "candidate_id": _candidate_id(sender_email=sender_email, sender_domain=sender_domain, list_id=list_id),
            "sender": sender,
            "sender_email": sender_email,
            "sender_domain": sender_domain,
            "representative_email_id": email_id,
            "sample_email_ids": [email_id],
            "recent_count": 1,
            "subjects": [subject],
            "method": method,
            "risk_level": _risk_level(method),
            "unsubscribe": {
                "one_click_url": classification.get("one_click_url"),
                "mailto_url": classification.get("mailto_url"),
                "website_url": classification.get("website_url"),
                "raw_list_unsubscribe": list_unsubscribe,
                "raw_list_unsubscribe_post": list_unsubscribe_post,
            },
            "status": "candidate",
            "evidence": evidence,
            "raw_tool_calls": {
                "get_email_headers": header_kwargs,
                "parse_list_unsubscribe_header": parse_kwargs,
                "classify_unsubscribe_method": classify_kwargs,
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
        f"include_body_links: {str(include_body_links).lower()}",
        f"matched_email_id_count: {len(email_ids)}",
        f"inspected_email_count: {inspected_count}",
        f"candidate_count: {len(ordered_candidates)}",
        f"metadata_error_count: {error_count}",
        "notes:",
        "- This is a read-only discovery result.",
        "- No unsubscribe action was executed.",
        "- No POST request, mailto message, website visit, browser automation, archive, or label action was performed.",
        "- Plain HTTP(S) unsubscribe URLs without List-Unsubscribe-Post are classified as website, not one_click.",
        "- When presenting candidates, include representative_email_id so a later confirmed execution can target the exact message.",
        "",
        "[SEARCH_EMAILS]",
        f"tool: search_emails",
        f"arguments: {search_kwargs}",
        search_text,
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
