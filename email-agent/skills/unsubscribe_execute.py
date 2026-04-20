from __future__ import annotations

import json
from typing import Any, Callable

from unsubscribe_state import (
    HIDDEN_STATUS,
    index_unsubscribe_state_records,
    load_unsubscribe_state_records,
    mark_candidates_hidden_after_unsubscribe,
    merge_discovered_candidates,
    visible_unsubscribe_state_records,
)
from unsubscribe_workflow import (
    DEFAULT_DAYS,
    DEFAULT_MAX_RESULTS,
    MAX_DAYS,
    MAX_RESULTS_CAP,
    build_evidence,
    build_targeted_search_query,
    call_tool,
    clamp_int,
    collect_candidates,
    extract_candidate_lists_from_read_results,
    loads_mapping,
    match_candidates_by_target_query,
    normalize_method,
    risk_level_for_method,
    sort_candidates,
)


ALLOWED_METHODS = {"auto", "one_click", "mailto", "website"}
MANUAL_LINK_FALLBACK_STATUSES = {"failed", "uncertain", "manual_required"}
SUCCESSFUL_HIDE_STATUSES = {"confirmed", "request_accepted", "request_submitted", "request_sent"}


def _normalize_requested_method(raw_method: Any) -> str:
    method = normalize_method(raw_method or "auto")
    if method not in ALLOWED_METHODS:
        return "auto"
    return method


def _normalize_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        raw_values = value
    elif value in {None, ""}:
        raw_values = []
    else:
        raw_values = [value]

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_values:
        item = str(raw_item or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def _state_record_to_candidate(record: dict[str, Any]) -> dict[str, Any]:
    representative_email_id = str(record.get("representative_email_id") or "").strip()
    sample_email_ids = list(record.get("sample_email_ids") or [])
    if representative_email_id and representative_email_id not in sample_email_ids:
        sample_email_ids = [representative_email_id, *sample_email_ids][:5]

    return {
        "candidate_id": str(record.get("candidate_id") or "").strip(),
        "sender": str(record.get("sender") or "").strip(),
        "sender_email": str(record.get("sender_email") or "").strip(),
        "sender_domain": str(record.get("sender_domain") or "").strip(),
        "representative_email_id": representative_email_id,
        "sample_email_ids": sample_email_ids,
        "recent_count": int(record.get("recent_count") or 1),
        "subjects": list(record.get("subjects") or []),
        "method": normalize_method(record.get("method")),
        "risk_level": risk_level_for_method(normalize_method(record.get("method"))),
        "status": str(record.get("status") or "").strip(),
    }


def _merge_current_candidates(
    read_result_candidates: list[dict[str, Any]],
    visible_state_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for candidate in visible_state_candidates:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if candidate_id:
            merged[candidate_id] = candidate
    for candidate in read_result_candidates:
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if candidate_id:
            merged[candidate_id] = candidate
    return sort_candidates(list(merged.values()))


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


def _hydrate_candidates_for_execution(
    candidates: list[dict[str, Any]],
    *,
    used_tools: dict[str, Callable[..., Any]],
) -> dict[str, Any]:
    email_ids: list[str] = []
    seen_email_ids: set[str] = set()
    for candidate in candidates:
        email_id = str(candidate.get("representative_email_id") or "").strip()
        if not email_id or email_id in seen_email_ids:
            continue
        seen_email_ids.add(email_id)
        email_ids.append(email_id)

    unsubscribe_kwargs = {"email_ids": email_ids}
    if email_ids:
        _, unsubscribe_kwargs, unsubscribe_text = call_tool(
            "get_unsubscribe_info",
            used_tools["get_unsubscribe_info"],
            unsubscribe_kwargs,
            log_prefix="[skill:unsubscribe_execute]",
        )
        unsubscribe_payload = loads_mapping(unsubscribe_text)
    else:
        unsubscribe_payload = {"items": [], "summary": {"requested_count": 0, "analyzed_count": 0, "error_count": 0}, "error": ""}
        unsubscribe_text = json.dumps(unsubscribe_payload, ensure_ascii=False)

    unsubscribe_items = {
        str(item.get("email_id") or "").strip(): item
        for item in unsubscribe_payload.get("items", [])
        if isinstance(item, dict) and str(item.get("email_id") or "").strip()
    }

    hydrated_candidates: list[dict[str, Any]] = []
    for candidate in candidates:
        hydrated = dict(candidate)
        email_id = str(candidate.get("representative_email_id") or "").strip()
        item = unsubscribe_items.get(email_id, {})
        unsubscribe = item.get("unsubscribe") if isinstance(item.get("unsubscribe"), dict) else {}
        item_error = str(item.get("error") or "").strip()
        method = normalize_method(unsubscribe.get("method") or candidate.get("method"))
        hydrated["unsubscribe"] = unsubscribe
        hydrated["method"] = method
        hydrated["risk_level"] = risk_level_for_method(method)
        hydrated["evidence"] = build_evidence(unsubscribe, item_error)
        hydrated_candidates.append(hydrated)

    return {
        "candidates": hydrated_candidates,
        "unsubscribe_kwargs": unsubscribe_kwargs,
        "unsubscribe_text": unsubscribe_text,
    }


def _execute_candidate(
    candidate: dict[str, Any],
    *,
    requested_method: str,
    used_tools: dict[str, Callable[..., Any]],
) -> dict[str, Any]:
    unsubscribe = candidate.get("unsubscribe") if isinstance(candidate.get("unsubscribe"), dict) else {}
    options = unsubscribe.get("options") if isinstance(unsubscribe.get("options"), dict) else {}
    classified_method = normalize_method(unsubscribe.get("method"))
    available_methods = _available_methods(options)
    effective_method = _resolve_effective_method(requested_method, classified_method, options)

    result = {
        "candidate_id": candidate.get("candidate_id"),
        "sender": candidate.get("sender"),
        "sender_email": candidate.get("sender_email"),
        "sender_domain": candidate.get("sender_domain"),
        "representative_email_id": candidate.get("representative_email_id"),
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
            tool_name, tool_kwargs, execution_text = call_tool(
                "post_one_click_unsubscribe",
                used_tools["post_one_click_unsubscribe"],
                {"url": one_click_url},
                log_prefix="[skill:unsubscribe_execute]",
            )
            execution_payload = loads_mapping(execution_text)
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
            tool_name, tool_kwargs, send_text = call_tool(
                "send",
                used_tools["send"],
                {
                    "to": str(send_payload.get("to") or "").strip(),
                    "subject": str(send_payload.get("subject") or "unsubscribe").strip() or "unsubscribe",
                    "body": body,
                },
                log_prefix="[skill:unsubscribe_execute]",
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

    if result.get("status") in MANUAL_LINK_FALLBACK_STATUSES and not result.get("manual_unsubscribe"):
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


def _candidate_summary(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidate_id": candidate.get("candidate_id"),
        "sender": candidate.get("sender"),
        "sender_email": candidate.get("sender_email"),
        "sender_domain": candidate.get("sender_domain"),
        "representative_email_id": candidate.get("representative_email_id"),
        "method": candidate.get("method"),
        "subjects": candidate.get("subjects"),
    }


def execute_skill(
    *,
    arguments,
    used_tools,
    skill_spec,
    read_results=None,
    skill_runtime=None,
    **_kwargs,
):
    days = clamp_int(arguments.get("days", DEFAULT_DAYS), default=DEFAULT_DAYS, minimum=1, maximum=MAX_DAYS)
    max_results = clamp_int(
        arguments.get("max_results", DEFAULT_MAX_RESULTS),
        default=DEFAULT_MAX_RESULTS,
        minimum=1,
        maximum=MAX_RESULTS_CAP,
    )
    requested_method = _normalize_requested_method(arguments.get("method", "auto"))
    target_queries = _normalize_string_list(arguments.get("target_queries"))
    candidate_ids = _normalize_string_list(arguments.get("candidate_ids"))

    if not target_queries and not candidate_ids:
        return {
            "completed": False,
            "reason": "unsubscribe_execute requires at least one target query or one candidate id.",
        }

    print(
        "[skill:unsubscribe_execute] start "
        f"days={days} max_results={max_results} method={requested_method} "
        f"target_queries={target_queries} candidate_ids={candidate_ids}",
        flush=True,
    )

    state_records = load_unsubscribe_state_records(skill_runtime=skill_runtime)
    state_index = index_unsubscribe_state_records(state_records)
    visible_state_candidates = sort_candidates(
        [_state_record_to_candidate(record) for record in visible_unsubscribe_state_records(state_records)]
    )
    read_result_candidates = extract_candidate_lists_from_read_results(read_results)
    current_visible_candidates = _merge_current_candidates(read_result_candidates, visible_state_candidates)
    current_visible_by_id = {
        str(candidate.get("candidate_id") or "").strip(): candidate for candidate in current_visible_candidates
    }

    target_requests: list[dict[str, Any]] = []
    for candidate_id in candidate_ids:
        target_requests.append(
            {
                "request_type": "candidate_id",
                "target_query": "",
                "candidate_id": candidate_id,
            }
        )
    for target_query in target_queries:
        target_requests.append(
            {
                "request_type": "query",
                "target_query": target_query,
                "candidate_id": "",
            }
        )

    fallback_discovery_summaries: list[dict[str, Any]] = []

    for request in target_requests:
        if request["request_type"] == "candidate_id":
            candidate = current_visible_by_id.get(request["candidate_id"]) or state_index.get(request["candidate_id"])
            if candidate is None:
                request["status"] = "not_found"
                request["reason"] = "The requested candidate_id was not present in the current subscription list or the local state."
            else:
                request["resolved_candidate"] = (
                    candidate if isinstance(candidate, dict) and "representative_email_id" in candidate else _state_record_to_candidate(candidate)
                )
                request["status"] = "resolved"
                request["selection_source"] = "candidate_id"
            continue

        target_query = request["target_query"]
        fallback_query = build_targeted_search_query(target_query, days)
        fallback_result = collect_candidates(
            search_query=fallback_query,
            max_results=max_results,
            used_tools=used_tools,
            log_prefix="[skill:unsubscribe_execute]",
        )
        merge_discovered_candidates(fallback_result["ordered_candidates"], skill_runtime=skill_runtime)
        fallback_matches = match_candidates_by_target_query(fallback_result["ordered_candidates"], target_query)

        fallback_summary = {
            "target_query": target_query,
            "search_query": fallback_query,
            "matched_email_id_count": len(fallback_result["matched_email_ids"]),
            "candidate_count": len(fallback_result["ordered_candidates"]),
            "resolved": False,
        }

        if len(fallback_matches) == 1:
            request["resolved_candidate"] = fallback_matches[0]
            request["status"] = "resolved"
            request["selection_source"] = "targeted_search_match"
            fallback_summary["resolved"] = True
            fallback_summary["selection_source"] = "targeted_search_match"
        elif fallback_matches:
            request["status"] = "not_found"
            request["reason"] = "The targeted mailbox search found multiple unsubscribe candidates for this request."
            fallback_summary["selection_source"] = "ambiguous_targeted_search_match"
        else:
            request["status"] = "not_found"
            request["reason"] = (
                "The target could not be matched to a discovered unsubscribe candidate "
                "after the targeted mailbox search."
            )
            fallback_summary["selection_source"] = "no_targeted_match"

        fallback_discovery_summaries.append(fallback_summary)

    state_records = load_unsubscribe_state_records(skill_runtime=skill_runtime)
    state_index = index_unsubscribe_state_records(state_records)

    candidates_to_execute: dict[str, dict[str, Any]] = {}
    already_unsubscribed: list[dict[str, Any]] = []
    unresolved_targets: list[dict[str, Any]] = []

    for request in target_requests:
        candidate = request.get("resolved_candidate")
        if not isinstance(candidate, dict):
            unresolved_targets.append(
                {
                    "target_query": request.get("target_query") or request.get("candidate_id") or "(unknown target)",
                    "status": request.get("status") or "not_found",
                    "reason": request.get("reason") or "The target could not be resolved.",
                }
            )
            continue

        candidate_id = str(candidate.get("candidate_id") or "").strip()
        state_record = state_index.get(candidate_id)
        if isinstance(state_record, dict) and state_record.get("status") == HIDDEN_STATUS:
            already_unsubscribed.append(
                {
                    "target_query": request.get("target_query") or "",
                    "selection_source": request.get("selection_source") or "local_state",
                    **_candidate_summary(_state_record_to_candidate(state_record)),
                    "local_status": HIDDEN_STATUS,
                }
            )
            continue

        if candidate_id:
            candidates_to_execute[candidate_id] = candidate

    hydrated_result = _hydrate_candidates_for_execution(
        list(candidates_to_execute.values()),
        used_tools=used_tools,
    )
    execution_results_by_candidate_id: dict[str, dict[str, Any]] = {}
    successful_candidates: list[dict[str, Any]] = []

    for hydrated_candidate in hydrated_result["candidates"]:
        execution_result = _execute_candidate(
            hydrated_candidate,
            requested_method=requested_method,
            used_tools=used_tools,
        )
        candidate_id = str(hydrated_candidate.get("candidate_id") or "").strip()
        if candidate_id:
            execution_results_by_candidate_id[candidate_id] = execution_result
        if execution_result.get("status") in SUCCESSFUL_HIDE_STATUSES:
            successful_candidates.append(hydrated_candidate)

    if successful_candidates:
        mark_candidates_hidden_after_unsubscribe(successful_candidates, skill_runtime=skill_runtime)

    final_state_records = load_unsubscribe_state_records(skill_runtime=skill_runtime)
    visible_after_execution = sort_candidates(
        [_state_record_to_candidate(record) for record in visible_unsubscribe_state_records(final_state_records)]
    )

    newly_unsubscribed: list[dict[str, Any]] = []
    manual_action_required: list[dict[str, Any]] = []
    failed_results: list[dict[str, Any]] = []
    target_results: list[dict[str, Any]] = []

    for request in target_requests:
        target_label = request.get("target_query") or request.get("candidate_id") or "(unknown target)"
        candidate = request.get("resolved_candidate")
        if not isinstance(candidate, dict):
            target_results.append(
                {
                    "target_query": target_label,
                    "status": "not_found",
                    "reason": request.get("reason") or "The target could not be resolved.",
                }
            )
            continue

        candidate_id = str(candidate.get("candidate_id") or "").strip()
        state_record = state_index.get(candidate_id)
        if isinstance(state_record, dict) and state_record.get("status") == HIDDEN_STATUS:
            target_results.append(
                {
                    "target_query": target_label,
                    "status": "already_unsubscribed",
                    "selection_source": request.get("selection_source") or "local_state",
                    **_candidate_summary(_state_record_to_candidate(state_record)),
                }
            )
            continue

        execution_result = execution_results_by_candidate_id.get(candidate_id)
        if execution_result is None:
            target_results.append(
                {
                    "target_query": target_label,
                    "status": "failed",
                    "selection_source": request.get("selection_source") or "resolved_candidate",
                    **_candidate_summary(candidate),
                    "reason": "The target candidate was resolved but no execution result was produced.",
                }
            )
            failed_results.append(target_results[-1])
            continue

        target_result = {
            "target_query": target_label,
            "selection_source": request.get("selection_source") or "resolved_candidate",
            **_candidate_summary(candidate),
            "execution_status": execution_result.get("status"),
            "requested_method": execution_result.get("requested_method"),
            "effective_method": execution_result.get("effective_method"),
            "evidence": execution_result.get("evidence"),
        }

        if execution_result.get("status") in SUCCESSFUL_HIDE_STATUSES:
            target_result["status"] = "newly_unsubscribed"
            newly_unsubscribed.append(target_result)
        elif execution_result.get("status") in {"manual_link_available", "manual_required"}:
            target_result["status"] = "manual_action_required"
            if execution_result.get("manual_unsubscribe"):
                target_result["manual_unsubscribe"] = execution_result["manual_unsubscribe"]
            manual_action_required.append(target_result)
        else:
            target_result["status"] = "failed"
            failed_results.append(target_result)

        target_results.append(target_result)

    lines = [
        "[UNSUBSCRIBE_EXECUTE_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'unsubscribe_execute')}",
        f"requested_method: {requested_method}",
        f"days: {days}",
        f"max_results: {max_results}",
        f"target_query_count: {len(target_queries)}",
        f"candidate_id_count: {len(candidate_ids)}",
        f"newly_unsubscribed_count: {len(newly_unsubscribed)}",
        f"already_unsubscribed_count: {len(already_unsubscribed)}",
        f"manual_action_required_count: {len(manual_action_required)}",
        f"failed_count: {len(failed_results)}",
        f"not_found_count: {len(unresolved_targets)}",
        "notes:",
        "- This workflow supports one or more unsubscribe targets.",
        "- It first tries to resolve targets from the current visible subscription list and local state.",
        "- If a target is not in the current list, it runs a targeted live mailbox search, re-inspects unsubscribe metadata, and merges any discovered candidates into the local state.",
        "- Successful one_click or mailto unsubscribe actions are marked hidden locally so later discovery results no longer show them.",
        "- Website unsubscribe automation is not implemented in this version.",
        "",
        "[CURRENT_VISIBLE_SUBSCRIPTIONS_JSON]",
        json.dumps(current_visible_candidates, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[EXECUTION_GET_UNSUBSCRIBE_INFO]",
        f"arguments: {hydrated_result['unsubscribe_kwargs']}",
        hydrated_result["unsubscribe_text"],
        "",
        "[FALLBACK_DISCOVERY_JSON]",
        json.dumps(fallback_discovery_summaries, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[TARGET_RESULTS_JSON]",
        json.dumps(target_results, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[NEWLY_UNSUBSCRIBED_JSON]",
        json.dumps(newly_unsubscribed, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[ALREADY_UNSUBSCRIBED_JSON]",
        json.dumps(already_unsubscribed, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[MANUAL_ACTION_REQUIRED_JSON]",
        json.dumps(manual_action_required, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[FAILED_JSON]",
        json.dumps(failed_results, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[NOT_FOUND_JSON]",
        json.dumps(unresolved_targets, ensure_ascii=False, indent=2, sort_keys=True),
        "",
        "[VISIBLE_SUBSCRIPTIONS_AFTER_EXECUTION_JSON]",
        json.dumps(visible_after_execution, ensure_ascii=False, indent=2, sort_keys=True),
    ]

    print(
        "[skill:unsubscribe_execute] completed "
        f"newly_unsubscribed={len(newly_unsubscribed)} already_unsubscribed={len(already_unsubscribed)} "
        f"manual_required={len(manual_action_required)} failed={len(failed_results)} not_found={len(unresolved_targets)}",
        flush=True,
    )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": (
            "Resolved unsubscribe targets against the current subscription list and local state, "
            "executed actionable targets, updated the local hidden overlay for successful unsubscribes, "
            "and returned categorized execution results."
        ),
    }
