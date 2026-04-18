from __future__ import annotations

from typing import Any, Callable


SEARCH_MAX_RESULTS = 350
UNANSWERED_MAX_RESULTS = 50
EVENT_MAX_RESULTS = 20


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:weekly_email_summary] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:weekly_email_summary] finished {name}", flush=True)
    return name, kwargs, text


def execute_skill(*, arguments, used_tools, skill_spec):
    raw_days = arguments.get("days", 7)
    days = int(raw_days)
    if days < 1:
        days = 1

    search_query = f"newer_than:{days}d"
    tasks = [
        ("get_my_identity", used_tools["get_my_identity"], {}),
        ("search_emails", used_tools["search_emails"], {"query": search_query, "max_results": SEARCH_MAX_RESULTS}),
        ("get_unanswered_emails", used_tools["get_unanswered_emails"], {"within_days": days, "max_results": UNANSWERED_MAX_RESULTS}),
        ("list_events", used_tools["list_events"], {"days_ahead": days, "max_results": EVENT_MAX_RESULTS}),
    ]

    results: dict[str, dict[str, Any]] = {}
    print(f"[skill:weekly_email_summary] start days={days}", flush=True)
    for name, tool_callable, kwargs in tasks:
        tool_name, tool_kwargs, text = _call_tool(name, tool_callable, kwargs)
        results[tool_name] = {"kwargs": tool_kwargs, "text": text}
    print("[skill:weekly_email_summary] collected all tool outputs", flush=True)

    ordered_sections = [
        ("GET_MY_IDENTITY", "get_my_identity"),
        ("SEARCH_EMAILS", "search_emails"),
        ("GET_UNANSWERED_EMAILS", "get_unanswered_emails"),
        ("LIST_EVENTS", "list_events"),
    ]

    lines = [
        "[WEEKLY_EMAIL_SUMMARY_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'weekly_email_summary')}",
        f"days: {days}",
        f"search_query: {search_query}",
        "ran_concurrently: false",
        f"search_max_results: {SEARCH_MAX_RESULTS}",
        f"unanswered_max_results: {UNANSWERED_MAX_RESULTS}",
        f"event_max_results: {EVENT_MAX_RESULTS}",
        "notes:",
        "- get_my_identity defines which email addresses belong to the mailbox owner.",
        "- search_emails is the primary mailbox scan.",
        "- Any email address returned by get_my_identity belongs to the mailbox owner, not an external correspondent.",
        "- The sections below are raw tool results for the finalizer LLM to summarize without adding new facts.",
    ]

    for section_name, result_key in ordered_sections:
        section = results.get(result_key, {})
        kwargs = section.get("kwargs", {})
        text = section.get("text", "(missing)")
        lines.extend(
            [
                "",
                f"[{section_name}]",
                f"tool: {result_key}",
                f"arguments: {kwargs}",
                text,
            ]
        )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": f"Collected weekly summary source data from identity, search, unanswered, and calendar tools for the last {days} day(s).",
    }
