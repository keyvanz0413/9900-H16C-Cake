from __future__ import annotations

import json
from typing import Any

from unsubscribe_state import (
    hidden_unsubscribe_state_records,
    merge_discovered_candidates,
    visible_unsubscribe_state_records,
)
from unsubscribe_workflow import (
    DEFAULT_DAYS,
    DEFAULT_MAX_RESULTS,
    MAX_DAYS,
    MAX_RESULTS_CAP,
    build_discovery_search_query,
    clamp_int,
    collect_candidates,
    sort_candidates,
)


def execute_skill(*, arguments, used_tools, skill_spec, skill_runtime=None, **_kwargs):
    days = clamp_int(arguments.get("days", DEFAULT_DAYS), default=DEFAULT_DAYS, minimum=1, maximum=MAX_DAYS)
    max_results = clamp_int(
        arguments.get("max_results", DEFAULT_MAX_RESULTS),
        default=DEFAULT_MAX_RESULTS,
        minimum=1,
        maximum=MAX_RESULTS_CAP,
    )
    search_query = build_discovery_search_query(days)

    print(
        f"[skill:unsubscribe_discovery] start days={days} max_results={max_results}",
        flush=True,
    )

    live_result = collect_candidates(
        search_query=search_query,
        max_results=max_results,
        used_tools=used_tools,
        log_prefix="[skill:unsubscribe_discovery]",
    )

    merge_result = merge_discovered_candidates(
        live_result["ordered_candidates"],
        skill_runtime=skill_runtime,
    )
    all_state_records = merge_result["items"]
    visible_candidates = sort_candidates(visible_unsubscribe_state_records(all_state_records))
    hidden_candidates = hidden_unsubscribe_state_records(all_state_records)

    lines = [
        "[UNSUBSCRIBE_DISCOVERY_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'unsubscribe_discovery')}",
        f"days: {days}",
        f"max_results: {max_results}",
        f"search_query: {search_query}",
        f"matched_email_id_count: {len(live_result['matched_email_ids'])}",
        f"live_discovered_candidate_count: {len(live_result['ordered_candidates'])}",
        f"inspected_email_count: {live_result['inspected_count']}",
        f"metadata_error_count: {live_result['error_count']}",
        f"state_inserted_count: {merge_result['inserted_count']}",
        f"state_updated_count: {merge_result['updated_count']}",
        f"visible_candidate_count: {len(visible_candidates)}",
        f"hidden_local_candidate_count: {len(hidden_candidates)}",
        "notes:",
        "- This workflow always does a live mailbox search before returning results.",
        "- Live discovery results are merged incrementally into the local subscription state.",
        "- Final user-visible candidates are filtered against the local state, so locally unsubscribed items are hidden even if live search finds them again.",
        "- No unsubscribe action was executed.",
        "- No POST request, mailto message, website visit, browser automation, archive, or label action was performed.",
        "- When presenting candidates, include representative_email_id so a later execution can target the exact sender candidate.",
        "",
        "[SEARCH_EMAILS]",
        "tool: search_emails",
        f"arguments: {live_result['search_kwargs']}",
        live_result["search_text"],
        "",
        "[GET_UNSUBSCRIBE_INFO]",
        "tool: get_unsubscribe_info",
        f"arguments: {live_result['unsubscribe_kwargs']}",
        live_result["unsubscribe_text"],
        "",
        "[VISIBLE_CANDIDATES_JSON]",
        json.dumps(visible_candidates, ensure_ascii=False, indent=2, sort_keys=True),
    ]

    print(
        "[skill:unsubscribe_discovery] completed "
        f"live_candidates={len(live_result['ordered_candidates'])} "
        f"visible_candidates={len(visible_candidates)} hidden_candidates={len(hidden_candidates)}",
        flush=True,
    )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": (
            "Ran live unsubscribe discovery, merged candidates into the local subscription state, "
            "and returned the filtered visible subscription list."
        ),
    }
