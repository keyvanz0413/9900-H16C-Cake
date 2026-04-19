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
ALLOWED_METHODS = {"auto", "one_click", "mailto", "website"}
MANUAL_LINK_FALLBACK_STATUSES = {"failed", "uncertain", "manual_required"}


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:unsubscribe_execute] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:unsubscribe_execute] finished {name}", flush=True)
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
    if method in {"mailto", "website"}:
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
    if method in {"one-click", "one click", "oneclick"}:
        return "one_click"
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


def _normalize_requested_method(raw_method: Any) -> str:
    method = _normalize_method(raw_method or "auto")
    if method not in ALLOWED_METHODS:
        return "auto"
    return method


def _available_methods(options: dict[str, Any]) -> list[str]:
    return [method for method in ("one_click", "mailto", "website") if isinstance(options.get(method), dict)]


def _resolve_effective_method(requested_method: str, classified_method: str, options: dict[str, Any]) -> str:
    available_methods = _available_methods(options)
    if requested_method != "auto":
        return requested_method
    if classified_method in available_methods:
        return classified_method
    if available_methods:
        return available_methods[0]
    return classified_method or "unknown"


def _first_manual_link(link_payload: dict[str, Any]) -> dict[str, Any]:
    links = link_payload.get("manual_links")
    if not isinstance(links, list):
        return {}
    for link in links:
        if not isinstance(link, dict):
            continue
        url = str(link.get("url") or "").strip()
        if url.lower().startswith(("http://", "https://")):
            return {
                "url": url,
                "label": str(link.get("label") or link.get("anchor_text") or "Open unsubscribe page").strip()
                or "Open unsubscribe page",
                "source": str(link.get("source") or "email_body").strip() or "email_body",
                "kind": str(link.get("kind") or "unsubscribe_link").strip() or "unsubscribe_link",
            }
    return {}


def _pending_result(candidate: dict[str, Any], requested_method: str) -> dict[str, Any]:
    unsubscribe = candidate.get("unsubscribe") if isinstance(candidate.get("unsubscribe"), dict) else {}
    options = unsubscribe.get("options") if isinstance(unsubscribe.get("options"), dict) else {}
    classified_method = _normalize_method(unsubscribe.get("method"))
    available_methods = _available_methods(options)
    return {
        "candidate_id": candidate.get("candidate_id"),
        "sender": candidate.get("sender"),
        "sender_email": candidate.get("sender_email"),
        "sender_domain": candidate.get("sender_domain"),
        "representative_email_id": candidate.get("representative_email_id"),
        "sample_email_ids": candidate.get("sample_email_ids"),
        "recent_count": candidate.get("recent_count"),
        "subjects": candidate.get("subjects"),
        "requested_method": requested_method,
        "classified_method": classified_method,
        "available_methods": available_methods,
        "status": "needs_confirmation",
        "evidence": "No unsubscribe action was executed because confirmed=false.",
    }


def _execute_candidate(
    candidate: dict[str, Any],
    *,
    requested_method: str,
    used_tools: dict[str, Callable[..., Any]],
) -> dict[str, Any]:
    unsubscribe = candidate.get("unsubscribe") if isinstance(candidate.get("unsubscribe"), dict) else {}
    options = unsubscribe.get("options") if isinstance(unsubscribe.get("options"), dict) else {}
    classified_method = _normalize_method(unsubscribe.get("method"))
    available_methods = _available_methods(options)
    effective_method = _resolve_effective_method(requested_method, classified_method, options)

    result = {
        "candidate_id": candidate.get("candidate_id"),
        "sender": candidate.get("sender"),
        "sender_email": candidate.get("sender_email"),
        "sender_domain": candidate.get("sender_domain"),
        "representative_email_id": candidate.get("representative_email_id"),
        "sample_email_ids": candidate.get("sample_email_ids"),
        "recent_count": candidate.get("recent_count"),
        "subjects": candidate.get("subjects"),
        "requested_method": requested_method,
        "classified_method": classified_method,
        "available_methods": available_methods,
        "effective_method": effective_method,
        "status": "failed",
        "sender_unsubscribe_status": "failed",
        "gmail_subscription_ui_status": "not_updated_by_agent",
        "evidence": "",
        "unsubscribe_info": unsubscribe,
        "tool_calls": {
            "execution_tool": "(none)",
            "execution_arguments": {},
        },
    }

    if requested_method != "auto" and requested_method not in available_methods:
        result["evidence"] = "Requested method is not available for this candidate."
        return result

    if effective_method == "one_click":
        one_click_option = options.get("one_click") if isinstance(options.get("one_click"), dict) else {}
        request_payload = (
            one_click_option.get("request_payload")
            if isinstance(one_click_option.get("request_payload"), dict)
            else {}
        )
        one_click_url = str(request_payload.get("url") or one_click_option.get("url") or "").strip()
        if not one_click_url:
            result["evidence"] = "No one-click URL was available after reading unsubscribe metadata."
        else:
            tool_name, tool_kwargs, execution_text = _call_tool(
                "post_one_click_unsubscribe",
                used_tools["post_one_click_unsubscribe"],
                {"url": one_click_url},
            )
            execution_payload = _loads_mapping(execution_text)
            result["status"] = str(execution_payload.get("status") or "uncertain")
            result["sender_unsubscribe_status"] = str(
                execution_payload.get("sender_unsubscribe_status")
                or execution_payload.get("status")
                or "uncertain"
            )
            result["gmail_subscription_ui_status"] = str(
                execution_payload.get("gmail_subscription_ui_status") or "not_updated_by_agent"
            )
            result["evidence"] = str(execution_payload.get("evidence") or "").strip()
            result["execution"] = execution_payload
            result["tool_calls"] = {
                "execution_tool": tool_name,
                "execution_arguments": tool_kwargs,
            }

    elif effective_method == "mailto":
        mailto_option = options.get("mailto") if isinstance(options.get("mailto"), dict) else {}
        send_payload = mailto_option.get("send_payload") if isinstance(mailto_option.get("send_payload"), dict) else {}
        if not send_payload:
            result["evidence"] = "No mailto send payload was available after reading unsubscribe metadata."
        else:
            body = str(send_payload.get("body") or "").strip() or "unsubscribe"
            tool_name, tool_kwargs, send_text = _call_tool(
                "send",
                used_tools["send"],
                {
                    "to": str(send_payload.get("to") or "").strip(),
                    "subject": str(send_payload.get("subject") or "unsubscribe").strip() or "unsubscribe",
                    "body": body,
                },
            )
            result["status"] = "request_sent"
            result["sender_unsubscribe_status"] = "request_sent"
            result["evidence"] = str(send_text or "Unsubscribe request email sent.").strip()
            result["execution"] = {
                "send_payload": {
                    "to": str(send_payload.get("to") or "").strip(),
                    "subject": str(send_payload.get("subject") or "unsubscribe").strip() or "unsubscribe",
                    "body": body,
                },
                "send_result": send_text,
            }
            result["tool_calls"] = {
                "execution_tool": tool_name,
                "execution_arguments": tool_kwargs,
            }

    elif effective_method == "website":
        website_option = options.get("website") if isinstance(options.get("website"), dict) else {}
        manual_unsubscribe = _first_manual_link(website_option)
        if not manual_unsubscribe:
            website_url = str(website_option.get("url") or "").strip()
            if website_url:
                manual_unsubscribe = {
                    "url": website_url,
                    "label": "Open unsubscribe page",
                    "source": "list_unsubscribe_header",
                    "kind": "unsubscribe_link",
                }
        result["status"] = "manual_link_available" if manual_unsubscribe else "manual_required"
        result["sender_unsubscribe_status"] = "manual_required"
        result["evidence"] = (
            "This candidate only exposes a website unsubscribe flow. "
            "Website unsubscribe automation is not implemented in this version."
        )
        if manual_unsubscribe:
            result["manual_unsubscribe"] = manual_unsubscribe

    else:
        result["evidence"] = f"Unsupported or unknown unsubscribe method: {effective_method}."

    manual_unsubscribe = result.get("manual_unsubscribe")
    if (
        not manual_unsubscribe
        and result.get("status") in MANUAL_LINK_FALLBACK_STATUSES
    ):
        website_option = options.get("website") if isinstance(options.get("website"), dict) else {}
        manual_unsubscribe = _first_manual_link(website_option)
        if manual_unsubscribe:
            result["manual_unsubscribe"] = manual_unsubscribe
            result["status"] = "manual_link_available"
            if result["sender_unsubscribe_status"] in {"failed", "manual_required", "uncertain"}:
                result["sender_unsubscribe_status"] = "manual_required"
            result["evidence"] = (
                f"{result['evidence']} Manual unsubscribe link is available for the user to open."
                if result["evidence"]
                else "Manual unsubscribe link is available for the user to open."
            )

    return result


def _status_counts(results: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in results:
        status = str(item.get("status") or "unknown").strip() or "unknown"
        counts[status] = counts.get(status, 0) + 1
    return counts


def execute_skill(*, arguments, used_tools, skill_spec):
    days = _clamp_int(arguments.get("days", DEFAULT_DAYS), default=DEFAULT_DAYS, minimum=1, maximum=MAX_DAYS)
    max_results = _clamp_int(
        arguments.get("max_results", DEFAULT_MAX_RESULTS),
        default=DEFAULT_MAX_RESULTS,
        minimum=1,
        maximum=MAX_RESULTS_CAP,
    )
    requested_method = _normalize_requested_method(arguments.get("method", "auto"))
    confirmed = bool(arguments.get("confirmed", False))
    search_query = _build_search_query(days)

    print(
        f"[skill:unsubscribe_execute] start days={days} max_results={max_results} method={requested_method} confirmed={confirmed}",
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

    if confirmed:
        execution_results = [
            _execute_candidate(candidate, requested_method=requested_method, used_tools=used_tools)
            for candidate in ordered_candidates
        ]
    else:
        execution_results = [
            _pending_result(candidate, requested_method)
            for candidate in ordered_candidates
        ]

    status_counts = _status_counts(execution_results)
    executed_candidate_count = sum(
        1 for item in execution_results if str(item.get("status") or "") != "needs_confirmation"
    )

    lines = [
        "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'unsubscribe_execute')}",
        f"days: {days}",
        f"max_results: {max_results}",
        f"requested_method: {requested_method}",
        f"confirmed: {str(confirmed).lower()}",
        f"search_query: {search_query}",
        f"matched_email_id_count: {len(email_ids)}",
        f"inspected_email_count: {inspected_count}",
        f"candidate_count: {len(ordered_candidates)}",
        f"metadata_error_count: {error_count}",
        f"executed_candidate_count: {executed_candidate_count}",
        f"status_counts: {json.dumps(status_counts, ensure_ascii=False, sort_keys=True)}",
        "notes:",
        "- This workflow reuses the same discovery pipeline as unsubscribe_discovery before any execution.",
        "- It searches recent subscription-like emails, reads execution-ready unsubscribe metadata, groups results into candidates, then executes per candidate.",
        "- one_click executes the sender endpoint POST and reports the returned HTTP result.",
        "- mailto sends the exact unsubscribe payload returned by get_unsubscribe_info.",
        "- Website unsubscribe automation is not implemented in this version.",
        "- Gmail Subscriptions UI is not updated by this agent; it may still show the sender after execution.",
        "- If status is manual_link_available, the user must open the extracted link manually; the agent did not visit the page.",
        "- If confirmed=false, no unsubscribe action was executed.",
        "",
        "[SEARCH_EMAILS]",
        "tool: search_emails",
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
        "",
        "[EXECUTION_RESULTS_JSON]",
        json.dumps(execution_results, ensure_ascii=False, indent=2, sort_keys=True),
    ]

    print(
        f"[skill:unsubscribe_execute] completed candidates={len(ordered_candidates)} executed={executed_candidate_count}",
        flush=True,
    )

    reason = (
        "Collected unsubscribe discovery metadata but did not execute because confirmed=false."
        if not confirmed
        else f"Executed unsubscribe workflow across {len(ordered_candidates)} discovered candidate(s)."
    )
    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": reason,
    }
