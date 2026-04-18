from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable


SEARCH_MAX_RESULTS = 20
MAX_SEARCH_LOOKBACK_DAYS = 30
UNANSWERED_WITHIN_DAYS = 7
UNANSWERED_MAX_RESULTS = 30
EMAIL_ID_PATTERN = re.compile(r"^\s*ID:\s*(\S+)\s*$", re.MULTILINE)
FROM_LINE_PATTERN = re.compile(r"^\d+\.\s+From:\s+(.+)$")
DEFAULT_WRITING_STYLE_CONTENT = "# Writing Style\n\n- No writing style profile yet."


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:draft_reply_from_email_context] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:draft_reply_from_email_context] finished {name}", flush=True)
    return name, kwargs, text


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


def _extract_email_address(raw_from: str) -> str:
    value = str(raw_from or "").strip()
    email_match = re.search(r"<([^>]+)>", value)
    if email_match:
        return email_match.group(1).strip()
    return value


def _extract_unanswered_entries(unanswered_output: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None

    for raw_line in str(unanswered_output or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        from_match = FROM_LINE_PATTERN.match(line)
        if from_match:
            if current and current.get("from") and current.get("subject"):
                entries.append(current)
            raw_from = from_match.group(1).strip()
            current = {
                "from": raw_from,
                "from_email": _extract_email_address(raw_from),
                "subject": "",
                "thread_id": "",
            }
            continue

        if current is None:
            continue

        if line.startswith("Subject:"):
            current["subject"] = line.removeprefix("Subject:").strip()
        elif line.startswith("Thread ID:"):
            current["thread_id"] = line.removeprefix("Thread ID:").strip()

    if current and current.get("from") and current.get("subject"):
        entries.append(current)

    return entries


def _escape_query_value(value: str) -> str:
    return str(value or "").replace("\\", "\\\\").replace('"', '\\"').strip()


def _build_search_query(query: str, days: int) -> str:
    normalized_query = str(query or "").strip()
    lowered = normalized_query.lower()
    if any(token in lowered for token in ("newer_than:", "after:", "before:", "in:inbox", "in:anywhere", "label:")):
        return normalized_query
    return f"in:inbox newer_than:{days}d ({normalized_query})"


def _build_unanswered_lookup_query(*, from_email: str, subject: str) -> str:
    escaped_subject = _escape_query_value(subject)
    return f'in:inbox newer_than:{UNANSWERED_WITHIN_DAYS}d from:{from_email} subject:"{escaped_subject}"'


def _normalize_selection_mode(raw_mode: Any) -> str:
    value = str(raw_mode or "").strip().lower()
    aliases = {
        "unanswered": "unanswered_rank",
        "unanswered_rank": "unanswered_rank",
        "search": "search_query",
        "query": "search_query",
        "search_query": "search_query",
    }
    return aliases.get(value, value)


def _resolve_writing_style_path(skill_runtime: dict[str, Any] | None) -> Path:
    runtime = skill_runtime or {}
    paths = runtime.get("paths") or {}
    raw_path = paths.get("writing_style_markdown")
    if raw_path:
        return Path(raw_path)
    return Path(__file__).resolve().parent.parent / "WRITING_STYLE.md"


def _read_writing_style_markdown(skill_runtime: dict[str, Any] | None) -> tuple[Path, str]:
    writing_style_path = _resolve_writing_style_path(skill_runtime)
    if not writing_style_path.exists():
        return writing_style_path, DEFAULT_WRITING_STYLE_CONTENT

    content = writing_style_path.read_text(encoding="utf-8").strip()
    if not content:
        return writing_style_path, DEFAULT_WRITING_STYLE_CONTENT
    return writing_style_path, content


def execute_skill(*, arguments, used_tools, skill_spec, skill_runtime=None):
    selection_mode = _normalize_selection_mode(arguments.get("selection_mode"))
    raw_target_rank = arguments.get("target_rank", 1)
    try:
        target_rank = int(raw_target_rank)
    except (TypeError, ValueError):
        target_rank = 1
    if target_rank < 1:
        target_rank = 1

    raw_days = arguments.get("days", 30)
    try:
        days = int(raw_days)
    except (TypeError, ValueError):
        days = 30
    if days < 1:
        days = 1
    if days > MAX_SEARCH_LOOKBACK_DAYS:
        days = MAX_SEARCH_LOOKBACK_DAYS

    writing_style_path, writing_style_markdown = _read_writing_style_markdown(skill_runtime)

    print(
        f"[skill:draft_reply_from_email_context] start selection_mode={selection_mode or '(empty)'} target_rank={target_rank} days={days}",
        flush=True,
    )

    target_email_id = ""
    target_body_kwargs: dict[str, Any] | None = None
    target_body_text = "(no target email body fetched)"
    mode_status = "pending"
    reason = ""

    search_kwargs: dict[str, Any] | None = None
    search_text = "(not run)"
    matched_email_ids: list[str] = []

    unanswered_kwargs: dict[str, Any] | None = None
    unanswered_text = "(not run)"
    unanswered_entries: list[dict[str, str]] = []
    selected_unanswered_entry: dict[str, str] | None = None
    lookup_kwargs: dict[str, Any] | None = None
    lookup_text = "(not run)"

    if selection_mode == "search_query":
        query = str(arguments.get("query") or "").strip()
        if not query:
            mode_status = "missing_query"
            reason = "selection_mode=search_query requires a non-empty query."
        else:
            search_query = _build_search_query(query, days)
            _, search_kwargs, search_text = _call_tool(
                "search_emails",
                used_tools["search_emails"],
                {"query": search_query, "max_results": SEARCH_MAX_RESULTS},
            )
            matched_email_ids = _extract_email_ids(search_text)
            if matched_email_ids:
                target_email_id = matched_email_ids[0]
                _, target_body_kwargs, target_body_text = _call_tool(
                    "get_email_body",
                    used_tools["get_email_body"],
                    {"email_id": target_email_id},
                )
                mode_status = "target_found"
                reason = "Located the target email from the provided search query and fetched its full body."
            else:
                mode_status = "no_search_match"
                reason = "The search query did not return any target email ids."

    elif selection_mode == "unanswered_rank":
        _, unanswered_kwargs, unanswered_text = _call_tool(
            "get_unanswered_emails",
            used_tools["get_unanswered_emails"],
            {"within_days": UNANSWERED_WITHIN_DAYS, "max_results": UNANSWERED_MAX_RESULTS},
        )
        unanswered_entries = _extract_unanswered_entries(unanswered_text)
        if target_rank > len(unanswered_entries):
            mode_status = "rank_out_of_range"
            reason = f"Requested unanswered rank {target_rank}, but only {len(unanswered_entries)} unanswered entries were available."
        else:
            selected_unanswered_entry = unanswered_entries[target_rank - 1]
            lookup_query = _build_unanswered_lookup_query(
                from_email=selected_unanswered_entry["from_email"],
                subject=selected_unanswered_entry["subject"],
            )
            _, lookup_kwargs, lookup_text = _call_tool(
                "search_emails",
                used_tools["search_emails"],
                {"query": lookup_query, "max_results": 1},
            )
            matched_email_ids = _extract_email_ids(lookup_text)
            if matched_email_ids:
                target_email_id = matched_email_ids[0]
                _, target_body_kwargs, target_body_text = _call_tool(
                    "get_email_body",
                    used_tools["get_email_body"],
                    {"email_id": target_email_id},
                )
                mode_status = "target_found"
                reason = "Located the requested unanswered email by rank, mapped it to a message id, and fetched its full body."
            else:
                mode_status = "lookup_failed"
                reason = "Found the unanswered entry but could not map it back to a message id."

    else:
        mode_status = "invalid_selection_mode"
        reason = "selection_mode must be unanswered_rank or search_query."

    print(
        f"[skill:draft_reply_from_email_context] completed status={mode_status} target_email_id={target_email_id or '(none)'}",
        flush=True,
    )

    lines = [
        "[DRAFT_REPLY_FROM_EMAIL_CONTEXT_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'draft_reply_from_email_context')}",
        f"selection_mode: {selection_mode or '(empty)'}",
        f"target_rank: {target_rank}",
        f"search_days: {days}",
        f"unanswered_within_days: {UNANSWERED_WITHIN_DAYS}",
        f"unanswered_max_results: {UNANSWERED_MAX_RESULTS}",
        f"mode_status: {mode_status}",
        f"target_email_id: {target_email_id or '(none)'}",
        "notes:",
        "- The final response should be a reply draft, not a summary.",
        "- Never claim the reply was sent.",
        "- Ground the draft only in the located target email, the associated metadata, and the fetched full body.",
        "- Mirror the user's writing style from the WRITING_STYLE section when drafting the reply.",
    ]

    if reason:
        lines.extend(["", "[WORKFLOW_REASON]", reason])

    lines.extend(
        [
            "",
            "[WRITING_STYLE]",
            f"path: {writing_style_path}",
            writing_style_markdown,
            "",
            "[SEARCH_RESULTS]",
            f"arguments: {search_kwargs if search_kwargs is not None else '(not run)'}",
            search_text,
            "",
            "[SEARCH_MATCHED_EMAIL_IDS]",
            ", ".join(matched_email_ids) if matched_email_ids else "(none)",
            "",
            "[UNANSWERED_RESULTS]",
            f"arguments: {unanswered_kwargs if unanswered_kwargs is not None else '(not run)'}",
            unanswered_text,
            "",
            "[SELECTED_UNANSWERED_ENTRY]",
        ]
    )

    if selected_unanswered_entry is None:
        lines.append("(none)")
    else:
        lines.extend(
            [
                f"from: {selected_unanswered_entry['from']}",
                f"subject: {selected_unanswered_entry['subject']}",
                f"thread_id: {selected_unanswered_entry.get('thread_id') or '(none)'}",
            ]
        )

    lines.extend(
        [
            "",
            "[UNANSWERED_LOOKUP_SEARCH]",
            f"arguments: {lookup_kwargs if lookup_kwargs is not None else '(not run)'}",
            lookup_text,
            "",
            "[TARGET_EMAIL_BODY]",
            f"arguments: {target_body_kwargs if target_body_kwargs is not None else '(not run)'}",
            target_body_text,
        ]
    )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": reason or "Collected mailbox context for reply drafting.",
    }
