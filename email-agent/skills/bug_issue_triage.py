from __future__ import annotations

import re
from typing import Any, Callable


SEARCH_MAX_RESULTS = 350
MAX_LOOKBACK_DAYS = 7
EMAIL_ID_PATTERN = re.compile(r"^\s*ID:\s*(\S+)\s*$", re.MULTILINE)
BUG_QUERY_TERMS = (
    "bug",
    "bugs",
    "defect",
    "regression",
    '"build failed"',
    '"build failure"',
    '"failing tests"',
    '"tests failed"',
    '"test failed"',
    '"ci failed"',
    '"pipeline failed"',
    '"issue opened"',
    '"incident opened"',
    '"production issue"',
    '"prod issue"',
    "incident",
    "outage",
    "broken",
    "failure",
    "blocker",
    '"error report"',
)


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:bug_issue_triage] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:bug_issue_triage] finished {name}", flush=True)
    return name, kwargs, text


def _build_bug_query(days: int) -> str:
    return f"in:inbox newer_than:{days}d ({' OR '.join(BUG_QUERY_TERMS)})"


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


def execute_skill(*, arguments, used_tools, skill_spec):
    raw_days = arguments.get("days", 7)
    days = int(raw_days)
    if days < 1:
        days = 1
    if days > MAX_LOOKBACK_DAYS:
        days = MAX_LOOKBACK_DAYS

    search_query = _build_bug_query(days)
    print(f"[skill:bug_issue_triage] start days={days}", flush=True)

    _, search_kwargs, search_text = _call_tool(
        "search_emails",
        used_tools["search_emails"],
        {"query": search_query, "max_results": SEARCH_MAX_RESULTS},
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

    print(
        "[skill:bug_issue_triage] collected "
        f"search_matches={len(matched_email_ids)} "
        f"body_fetches={len(body_results)}",
        flush=True,
    )

    lines = [
        "[BUG_ISSUE_TRIAGE_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'bug_issue_triage')}",
        f"days: {days}",
        f"search_query: {search_query}",
        f"bug_keywords: {', '.join(BUG_QUERY_TERMS)}",
        f"max_lookback_days: {MAX_LOOKBACK_DAYS}",
        f"search_max_results: {SEARCH_MAX_RESULTS}",
        f"matched_email_count: {len(matched_email_ids)}",
        f"body_fetch_count: {len(body_results)}",
        "notes:",
        "- The lookback window is capped at 7 days.",
        "- search_emails scans the inbox for bug-related, build-failure, test-failure, regression, issue-opened, incident, outage, blocker, and broken-workflow English keywords.",
        "- The matched emails may include engineering notifications, task records, CI alerts, issue trackers, or other bug-related inbox items.",
        "- get_email_body is fetched for every matched email id returned by the search results.",
        "- Finalizer instruction: rank the resulting bug items from highest priority to lowest priority before presenting them to the user.",
        "- Prioritize production-impacting regressions, outages, blockers, build failures, and failing tests ahead of lower-signal informational items when the raw tool output supports that ordering.",
        "- The sections below are raw tool outputs for the finalizer LLM to summarize without adding new facts.",
        "",
        "[SEARCH_EMAILS]",
        "tool: search_emails",
        f"arguments: {search_kwargs}",
        search_text,
        "",
        "[MATCHED_BUG_EMAIL_IDS]",
        ", ".join(matched_email_ids) if matched_email_ids else "(none)",
        "",
        "[EMAIL_BODY_RESULTS]",
        f"count: {len(body_results)}",
    ]

    if not body_results:
        lines.append("(no matched bug-related email ids were available for get_email_body)")
    else:
        for index, body_result in enumerate(body_results, start=1):
            lines.extend(
                [
                    "",
                    f"[EMAIL_BODY_{index}]",
                    "tool: get_email_body",
                    f"email_id: {body_result['email_id']}",
                    f"arguments: {body_result['kwargs']}",
                    body_result["text"],
                ]
            )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": (
            f"Collected bug-related search hits and fetched full bodies for "
            f"{len(matched_email_ids)} matched email(s) within the last {days} day(s)."
        ),
    }
