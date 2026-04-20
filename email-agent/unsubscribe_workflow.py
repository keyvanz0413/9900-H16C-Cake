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


def call_tool(
    name: str,
    tool_callable: Callable[..., Any],
    kwargs: dict[str, Any],
    *,
    log_prefix: str,
) -> tuple[str, dict[str, Any], str]:
    print(f"{log_prefix} calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"{log_prefix} finished {name}", flush=True)
    return name, kwargs, text


def loads_mapping(raw_text: str) -> dict[str, Any]:
    try:
        payload = json.loads(str(raw_text or "").strip())
    except json.JSONDecodeError:
        return {}
    if isinstance(payload, dict):
        return payload
    return {}


def clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if number < minimum:
        return minimum
    if number > maximum:
        return maximum
    return number


def build_discovery_search_query(days: int) -> str:
    return (
        f'in:inbox newer_than:{days}d '
        '(unsubscribe OR newsletter OR subscription OR "manage preferences" OR "email preferences" OR marketing)'
    )


def build_targeted_search_query(target_query: str, days: int) -> str:
    return f'in:inbox newer_than:{days}d ({target_query})'


def extract_email_ids(search_output: str) -> list[str]:
    email_ids: list[str] = []
    seen: set[str] = set()
    for raw_email_id in EMAIL_ID_PATTERN.findall(str(search_output or "")):
        email_id = raw_email_id.strip()
        if not email_id or email_id in seen:
            continue
        seen.add(email_id)
        email_ids.append(email_id)
    return email_ids


def extract_search_entries(search_output: str) -> list[dict[str, str]]:
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
        for email_id in extract_email_ids(search_output)
    ]


def sender_parts(raw_from: str) -> tuple[str, str, str]:
    display_name, email_address = parseaddr(str(raw_from or "").strip())
    sender_email = email_address.strip().lower()
    sender_domain = sender_email.rsplit("@", 1)[-1] if "@" in sender_email else ""
    sender = str(raw_from or "").strip() or sender_email or "(unknown sender)"
    if not sender and display_name:
        sender = display_name
    return sender, sender_email, sender_domain


def candidate_id_for_sender(*, sender_email: str, sender_domain: str) -> str:
    stable_source = "|".join([sender_email, sender_domain]).strip("|") or "unknown"
    digest = hashlib.sha1(stable_source.encode("utf-8")).hexdigest()[:12]
    readable = sender_email or sender_domain or "unknown"
    readable = re.sub(r"[^a-zA-Z0-9_.@-]+", "-", readable).strip("-")[:48] or "unknown"
    return f"{readable}:{digest}"


def risk_level_for_method(method: str) -> str:
    if method == "one_click":
        return "low"
    if method in {"mailto", "website"}:
        return "medium"
    if method == "multiple":
        return "review"
    return "unknown"


def normalize_method(raw_method: Any) -> str:
    method = str(raw_method or "unknown").strip().lower()
    if method in {"one-click", "one click", "oneclick"}:
        return "one_click"
    return method or "unknown"


def _best_method(existing: str, incoming: str) -> str:
    existing_priority = METHOD_PRIORITY.get(existing, METHOD_PRIORITY["unknown"])
    incoming_priority = METHOD_PRIORITY.get(incoming, METHOD_PRIORITY["unknown"])
    return incoming if incoming_priority < existing_priority else existing


def build_evidence(unsubscribe: dict[str, Any], item_error: str) -> list[str]:
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


def merge_candidate(candidates: dict[str, dict[str, Any]], candidate: dict[str, Any]) -> None:
    key = str(candidate.get("candidate_id") or "").strip()
    if not key:
        return

    existing = candidates.get(key)
    if existing is None:
        candidates[key] = candidate
        return

    existing["recent_count"] = int(existing.get("recent_count") or 0) + int(candidate.get("recent_count") or 1)
    for subject in candidate.get("subjects", []):
        if subject and subject not in existing["subjects"] and len(existing["subjects"]) < 5:
            existing["subjects"].append(subject)
    for email_id in candidate.get("sample_email_ids", []):
        if email_id and email_id not in existing["sample_email_ids"] and len(existing["sample_email_ids"]) < 5:
            existing["sample_email_ids"].append(email_id)

    chosen_method = _best_method(
        str(existing.get("method") or "unknown"),
        str(candidate.get("method") or "unknown"),
    )
    if chosen_method != existing.get("method"):
        existing["method"] = chosen_method
        existing["risk_level"] = risk_level_for_method(chosen_method)
        existing["representative_email_id"] = candidate.get("representative_email_id")
        existing["unsubscribe"] = candidate.get("unsubscribe")
        existing["evidence"] = candidate.get("evidence")


def sort_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        candidates,
        key=lambda item: (
            METHOD_PRIORITY.get(str(item.get("method") or "unknown"), METHOD_PRIORITY["unknown"]),
            -int(item.get("recent_count") or 0),
            str(item.get("sender_email") or item.get("sender") or item.get("candidate_id") or ""),
        ),
    )


def build_empty_unsubscribe_payload() -> dict[str, Any]:
    return {
        "items": [],
        "summary": {
            "requested_count": 0,
            "analyzed_count": 0,
            "error_count": 0,
        },
        "error": "",
    }


def collect_candidates(
    *,
    search_query: str,
    max_results: int,
    used_tools: dict[str, Callable[..., Any]],
    log_prefix: str,
) -> dict[str, Any]:
    _, search_kwargs, search_text = call_tool(
        "search_emails",
        used_tools["search_emails"],
        {"query": search_query, "max_results": max_results},
        log_prefix=log_prefix,
    )
    search_entries = extract_search_entries(search_text)
    email_ids = [entry["email_id"] for entry in search_entries if entry.get("email_id")]
    if not email_ids:
        email_ids = extract_email_ids(search_text)
        search_entries = [
            {"from": "(unknown sender)", "subject": "(no subject)", "email_id": email_id}
            for email_id in email_ids
        ]

    unsubscribe_kwargs = {"email_ids": email_ids}
    if email_ids:
        _, unsubscribe_kwargs, unsubscribe_text = call_tool(
            "get_unsubscribe_info",
            used_tools["get_unsubscribe_info"],
            unsubscribe_kwargs,
            log_prefix=log_prefix,
        )
        unsubscribe_payload = loads_mapping(unsubscribe_text)
    else:
        unsubscribe_payload = build_empty_unsubscribe_payload()
        unsubscribe_text = json.dumps(unsubscribe_payload, ensure_ascii=False)

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
        sender, sender_email, sender_domain = sender_parts(raw_from)
        subject = str(entry.get("subject") or "").strip() or "(no subject)"
        method = normalize_method(unsubscribe.get("method"))
        evidence = build_evidence(unsubscribe, item_error)

        candidate = {
            "candidate_id": candidate_id_for_sender(sender_email=sender_email, sender_domain=sender_domain),
            "sender": sender,
            "sender_email": sender_email,
            "sender_domain": sender_domain,
            "representative_email_id": email_id,
            "sample_email_ids": [email_id],
            "recent_count": 1,
            "subjects": [subject],
            "method": method,
            "risk_level": risk_level_for_method(method),
            "unsubscribe": unsubscribe,
            "status": "candidate",
            "evidence": evidence,
            "raw_tool_calls": {
                "get_unsubscribe_info": unsubscribe_kwargs,
            },
        }
        merge_candidate(candidates, candidate)
        inspected_count += 1

    ordered_candidates = sort_candidates(list(candidates.values()))
    return {
        "search_query": search_query,
        "search_kwargs": search_kwargs,
        "search_text": search_text,
        "matched_email_ids": email_ids,
        "unsubscribe_kwargs": unsubscribe_kwargs,
        "unsubscribe_text": unsubscribe_text,
        "ordered_candidates": ordered_candidates,
        "inspected_count": inspected_count,
        "error_count": error_count,
    }


def normalize_target_query(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().split())


def candidate_fragments(candidate: dict[str, Any]) -> list[str]:
    fragments: list[str] = []
    for key in ("candidate_id", "sender", "sender_email", "sender_domain"):
        value = normalize_target_query(candidate.get(key))
        if value:
            fragments.append(value)
    for subject in candidate.get("subjects", []):
        value = normalize_target_query(subject)
        if value:
            fragments.append(value)
    return fragments


def match_candidates_by_target_query(candidates: list[dict[str, Any]], target_query: str) -> list[dict[str, Any]]:
    normalized_target = normalize_target_query(target_query)
    if not normalized_target:
        return []

    exact_matches: list[dict[str, Any]] = []
    partial_matches: list[dict[str, Any]] = []
    for candidate in candidates:
        fragments = candidate_fragments(candidate)
        if not fragments:
            continue
        if any(fragment == normalized_target for fragment in fragments):
            exact_matches.append(candidate)
            continue
        if any(normalized_target in fragment or fragment in normalized_target for fragment in fragments):
            partial_matches.append(candidate)

    return exact_matches or partial_matches


def extract_section_text(raw_text: str, section_name: str) -> str:
    pattern = re.compile(
        rf"(?ms)^\[{re.escape(section_name)}\]\s*\n(.*?)(?=^\[[A-Z0-9_]+\]\s*\n|\Z)"
    )
    match = pattern.search(str(raw_text or ""))
    if not match:
        return ""
    return str(match.group(1) or "").strip()


def extract_candidate_lists_from_read_results(read_results: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if not isinstance(read_results, list):
        return []

    collected: dict[str, dict[str, Any]] = {}
    section_names = (
        "VISIBLE_CANDIDATES_JSON",
        "VISIBLE_SUBSCRIPTIONS_AFTER_EXECUTION_JSON",
    )
    for result in read_results:
        if not isinstance(result, dict):
            continue
        artifact = result.get("artifact") if isinstance(result.get("artifact"), dict) else {}
        artifact_data = artifact.get("data") if isinstance(artifact.get("data"), dict) else {}
        raw_text = str(artifact_data.get("response") or artifact.get("summary") or "").strip()
        if not raw_text:
            continue

        for section_name in section_names:
            section_text = extract_section_text(raw_text, section_name)
            if not section_text:
                continue
            try:
                payload = json.loads(section_text)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, list):
                continue
            for item in payload:
                if not isinstance(item, dict):
                    continue
                candidate_id = str(item.get("candidate_id") or "").strip()
                if not candidate_id:
                    continue
                collected[candidate_id] = item

    return sort_candidates(list(collected.values()))
