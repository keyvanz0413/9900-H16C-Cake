from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Callable


SEARCH_MAX_RESULTS = 350
MAX_LOOKBACK_DAYS = 7
EMAIL_ID_PATTERN = re.compile(r"^\s*ID:\s*(\S+)\s*$", re.MULTILINE)
MESSAGE_ID_PATTERN = re.compile(r"^\s*Message ID:\s*(\S+)\s*$", re.MULTILINE)
SEARCH_ENTRY_START_PATTERN = re.compile(r"^\d+\.\s")
EMAIL_ADDRESS_PATTERN = re.compile(r"<([^>]+@[^>]+)>")
RESUME_QUERY_TERMS = (
    "candidate",
    "applicant",
    "application",
    "resume",
    "cv",
    "portfolio",
    '"job application"',
    '"application for"',
    '"applying for"',
    '"cover letter"',
    '"candidate profile"',
    '"candidate submission"',
    '"resume attached"',
    '"cv attached"',
)
FOLLOW_UP_PREVIEW_HINTS = (
    "english version",
    "english resume",
    "send your english",
    "could you send",
    "please send",
    "follow up",
    "following up",
)


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:resume_candidate_review] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:resume_candidate_review] finished {name}", flush=True)
    return name, kwargs, text


def _quote_query_term(value: str) -> str:
    normalized = " ".join(str(value or "").strip().split())
    if not normalized:
        return ""
    escaped = normalized.replace('"', "")
    if " " in escaped:
        return f'"{escaped}"'
    return escaped


def _build_default_resume_query(days: int) -> str:
    return f"in:inbox newer_than:{days}d ({' OR '.join(RESUME_QUERY_TERMS)})"


def _build_query_from_candidate_names(candidate_names: list[str], *, mailbox_scope: str) -> str:
    cleaned_names = [_quote_query_term(name) for name in candidate_names if str(name or "").strip()]
    names_clause = " OR ".join(name for name in cleaned_names if name)
    resume_clause = " OR ".join(RESUME_QUERY_TERMS)
    scope_prefix = "in:inbox " if mailbox_scope == "inbox" else ""
    if not names_clause:
        return f"{scope_prefix}({resume_clause})".strip()
    return f"{scope_prefix}({names_clause}) ({resume_clause})".strip()


def _apply_mailbox_scope(query: str, *, mailbox_scope: str) -> str:
    normalized_query = " ".join(str(query or "").strip().split())
    if not normalized_query:
        return ""
    if mailbox_scope == "inbox" and "in:inbox" not in normalized_query:
        return f"in:inbox ({normalized_query})"
    return normalized_query


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


def _extract_message_ids(text: str) -> list[str]:
    matched_ids: list[str] = []
    seen_ids: set[str] = set()
    for raw_email_id in MESSAGE_ID_PATTERN.findall(str(text or "")):
        email_id = raw_email_id.strip()
        if not email_id or email_id in seen_ids:
            continue
        seen_ids.add(email_id)
        matched_ids.append(email_id)
    return matched_ids


def _attachment_list_has_files(attachments_output: str) -> bool:
    lowered = str(attachments_output or "").strip().lower()
    return bool(lowered) and not lowered.startswith("no attachments in this email")


def _extract_relevant_attachment_text_sections(
    attachment_tool_output: str,
    *,
    relevant_message_ids: list[str],
) -> str:
    text = str(attachment_tool_output or "").strip()
    if not text or not relevant_message_ids:
        return ""

    lines = text.splitlines()
    preamble: list[str] = []
    sections: list[tuple[str, str]] = []
    current_section: list[str] = []
    current_message_id = ""
    in_email_sections = False

    for line in lines:
        if line.startswith("[EMAIL_"):
            in_email_sections = True
            if current_section:
                sections.append((current_message_id, "\n".join(current_section).strip()))
            current_section = [line]
            current_message_id = ""
            continue

        if in_email_sections:
            current_section.append(line)
            if line.startswith("Message ID:"):
                current_message_id = line.split(":", 1)[1].strip()
            continue

        preamble.append(line)

    if current_section:
        sections.append((current_message_id, "\n".join(current_section).strip()))

    selected_sections = [
        section_text
        for message_id, section_text in sections
        if message_id in set(relevant_message_ids)
    ]
    if not selected_sections:
        return ""

    filtered_lines = [
        "[RELEVANT_ATTACHMENT_TEXT_EXTRACTIONS]",
        "tool: extract_recent_attachment_texts",
        f"matched_message_ids: {', '.join(relevant_message_ids)}",
    ]
    if preamble:
        filtered_lines.extend(["[ATTACHMENT_EXTRACTION_PREAMBLE]", "\n".join(preamble).strip()])
    for section_text in selected_sections:
        filtered_lines.extend(["", section_text])
    return "\n".join(filtered_lines).strip()


def _parse_search_results(search_output: str) -> dict[str, dict[str, str]]:
    text = str(search_output or "").strip()
    if not text:
        return {}

    entries: list[list[str]] = []
    current: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if SEARCH_ENTRY_START_PATTERN.match(line):
            if current:
                entries.append(current)
            current = [line]
            continue
        if current:
            current.append(line)
    if current:
        entries.append(current)

    metadata_by_id: dict[str, dict[str, str]] = {}
    for entry_lines in entries:
        block = "\n".join(entry_lines)
        email_id_matches = EMAIL_ID_PATTERN.findall(block)
        if not email_id_matches:
            continue
        email_id = email_id_matches[-1].strip()
        metadata: dict[str, str] = {"raw": block}
        for line in entry_lines:
            stripped = line.strip()
            if "From:" in stripped:
                metadata["from"] = stripped.split("From:", 1)[1].strip()
            elif stripped.startswith("Subject:"):
                metadata["subject"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Preview:"):
                metadata["preview"] = stripped.split(":", 1)[1].strip()
            elif stripped.startswith("Date:"):
                metadata["date"] = stripped.split(":", 1)[1].strip()
        metadata_by_id[email_id] = metadata
    return metadata_by_id


def _normalize_subject(subject: str) -> str:
    normalized = str(subject or "").strip()
    while True:
        updated = re.sub(r"^(?:(?:re|fwd?|fw)\s*:\s*)", "", normalized, flags=re.IGNORECASE).strip()
        if updated == normalized:
            return normalized.lower()
        normalized = updated


def _looks_like_follow_up(metadata: dict[str, str]) -> bool:
    subject = str(metadata.get("subject") or "").strip().lower()
    preview = str(metadata.get("preview") or "").strip().lower()
    if subject.startswith(("re:", "fw:", "fwd:")):
        return True
    return any(hint in preview for hint in FOLLOW_UP_PREVIEW_HINTS)


def _group_key_for_email(email_id: str, metadata_by_id: dict[str, dict[str, str]]) -> str:
    metadata = metadata_by_id.get(email_id) or {}
    subject = _normalize_subject(metadata.get("subject") or "")
    if subject:
        return subject
    return email_id


def _classify_candidate_hits(
    email_ids: list[str],
    *,
    metadata_by_id: dict[str, dict[str, str]],
    attachment_results_by_id: dict[str, dict[str, Any]],
) -> tuple[list[str], list[str]]:
    grouped_ids: dict[str, list[str]] = defaultdict(list)
    for email_id in email_ids:
        grouped_ids[_group_key_for_email(email_id, metadata_by_id)].append(email_id)

    primary_ids: list[str] = []
    context_ids: list[str] = []
    for group_email_ids in grouped_ids.values():
        attachment_primary_ids = [
            email_id
            for email_id in group_email_ids
            if bool((attachment_results_by_id.get(email_id) or {}).get("has_attachments"))
        ]
        if attachment_primary_ids:
            primary_ids.extend(attachment_primary_ids)
            context_ids.extend([email_id for email_id in group_email_ids if email_id not in attachment_primary_ids])
            continue

        non_follow_up_ids = [
            email_id for email_id in group_email_ids if not _looks_like_follow_up(metadata_by_id.get(email_id) or {})
        ]
        chosen_primary_id = (non_follow_up_ids or group_email_ids[:1])[0]
        primary_ids.append(chosen_primary_id)
        context_ids.extend([email_id for email_id in group_email_ids if email_id != chosen_primary_id])

    return primary_ids, context_ids


def _recover_search_context_from_read_results(read_results: list[dict[str, Any]] | None) -> tuple[list[str], dict[str, dict[str, str]]]:
    recovered_email_ids: list[str] = []
    recovered_metadata: dict[str, dict[str, str]] = {}
    seen_ids: set[str] = set()

    for result in read_results or []:
        artifact = result.get("artifact") if isinstance(result, dict) else None
        if not isinstance(artifact, dict):
            continue

        candidate_texts: list[str] = []
        summary = artifact.get("summary")
        if isinstance(summary, str) and summary.strip():
            candidate_texts.append(summary)

        data = artifact.get("data")
        if isinstance(data, dict):
            response = data.get("response")
            if isinstance(response, str) and response.strip():
                candidate_texts.append(response)

        for text in candidate_texts:
            for email_id in _extract_email_ids(text) + _extract_message_ids(text):
                if email_id in seen_ids:
                    continue
                seen_ids.add(email_id)
                recovered_email_ids.append(email_id)
            recovered_metadata.update(_parse_search_results(text))

    return recovered_email_ids, recovered_metadata


def _build_query_from_metadata(email_ids: list[str], metadata_by_id: dict[str, dict[str, str]], *, mailbox_scope: str) -> str:
    clauses: list[str] = []
    for email_id in email_ids:
        metadata = metadata_by_id.get(email_id) or {}
        sender = str(metadata.get("from") or "").strip()
        subject = str(metadata.get("subject") or "").strip()
        sender_email_match = EMAIL_ADDRESS_PATTERN.search(sender)
        if sender_email_match:
            clauses.append(f"from:{sender_email_match.group(1)}")
        elif sender:
            clauses.append(_quote_query_term(sender))
        if subject:
            clauses.append(f"subject:{_quote_query_term(subject)}")

    deduped_clauses: list[str] = []
    seen_clauses: set[str] = set()
    for clause in clauses:
        if not clause or clause in seen_clauses:
            continue
        seen_clauses.add(clause)
        deduped_clauses.append(clause)

    if not deduped_clauses:
        return ""
    joined = " OR ".join(deduped_clauses)
    return _apply_mailbox_scope(f"({joined})", mailbox_scope=mailbox_scope)


def _format_email_id_list(email_ids: list[str]) -> str:
    return ", ".join(email_ids) if email_ids else "(none)"


def execute_skill(*, arguments, used_tools, skill_spec, read_results=None):
    raw_days = arguments.get("days", 7)
    days = int(raw_days)
    if days < 1:
        days = 1
    if days > MAX_LOOKBACK_DAYS:
        days = MAX_LOOKBACK_DAYS

    mailbox_scope = str(arguments.get("mailbox_scope") or "inbox").strip().lower() or "inbox"
    if mailbox_scope not in {"inbox", "all"}:
        mailbox_scope = "inbox"

    explicit_email_ids = [str(item).strip() for item in arguments.get("email_ids", []) if str(item).strip()]
    explicit_query = str(arguments.get("query") or "").strip()
    candidate_names = [str(item).strip() for item in arguments.get("candidate_names", []) if str(item).strip()]

    recovered_email_ids, recovered_metadata = _recover_search_context_from_read_results(read_results)
    matched_email_ids = list(explicit_email_ids or recovered_email_ids)
    metadata_by_id = dict(recovered_metadata)

    execution_mode = "recent_scan"
    search_query = ""
    search_kwargs: dict[str, Any] | None = None
    search_text = ""

    if matched_email_ids:
        execution_mode = "email_ids"
    else:
        if explicit_query:
            execution_mode = "query"
            search_query = _apply_mailbox_scope(explicit_query, mailbox_scope=mailbox_scope)
        elif candidate_names:
            execution_mode = "candidate_names"
            search_query = _build_query_from_candidate_names(candidate_names, mailbox_scope=mailbox_scope)
        else:
            execution_mode = "recent_scan"
            search_query = _build_default_resume_query(days)

        print(
            f"[skill:resume_candidate_review] start days={days} mode={execution_mode} mailbox_scope={mailbox_scope}",
            flush=True,
        )
        _, search_kwargs, search_text = _call_tool(
            "search_emails",
            used_tools["search_emails"],
            {"query": search_query, "max_results": SEARCH_MAX_RESULTS},
        )
        matched_email_ids = _extract_email_ids(search_text)
        metadata_by_id.update(_parse_search_results(search_text))

    attachment_check_results: list[dict[str, Any]] = []
    attachment_results_by_id: dict[str, dict[str, Any]] = {}
    for email_id in matched_email_ids:
        _, attachment_kwargs, attachment_text = _call_tool(
            "get_email_attachments",
            used_tools["get_email_attachments"],
            {"email_id": email_id},
        )
        has_attachments = _attachment_list_has_files(attachment_text)
        record = {
            "email_id": email_id,
            "kwargs": attachment_kwargs,
            "text": attachment_text,
            "has_attachments": has_attachments,
        }
        attachment_check_results.append(record)
        attachment_results_by_id[email_id] = record

    primary_candidate_email_ids, thread_context_email_ids = _classify_candidate_hits(
        matched_email_ids,
        metadata_by_id=metadata_by_id,
        attachment_results_by_id=attachment_results_by_id,
    )
    primary_candidate_email_ids_with_attachments = [
        email_id
        for email_id in primary_candidate_email_ids
        if bool((attachment_results_by_id.get(email_id) or {}).get("has_attachments"))
    ]

    attachment_extraction_kwargs: dict[str, Any] | None = None
    attachment_extraction_text = ""
    filtered_attachment_extraction_text = ""
    attachment_extraction_query = ""
    if primary_candidate_email_ids_with_attachments:
        if search_query:
            attachment_extraction_query = f"{search_query} has:attachment"
        else:
            attachment_extraction_query = _build_query_from_metadata(
                primary_candidate_email_ids_with_attachments,
                metadata_by_id,
                mailbox_scope=mailbox_scope,
            )
            if attachment_extraction_query:
                attachment_extraction_query = f"{attachment_extraction_query} has:attachment"

        if attachment_extraction_query:
            _, attachment_extraction_kwargs, attachment_extraction_text = _call_tool(
                "extract_recent_attachment_texts",
                used_tools["extract_recent_attachment_texts"],
                {"query": attachment_extraction_query, "max_results": SEARCH_MAX_RESULTS},
            )
            filtered_attachment_extraction_text = _extract_relevant_attachment_text_sections(
                attachment_extraction_text,
                relevant_message_ids=primary_candidate_email_ids_with_attachments,
            )

    print(
        "[skill:resume_candidate_review] collected "
        f"mode={execution_mode} "
        f"search_matches={len(matched_email_ids)} "
        f"primary_hits={len(primary_candidate_email_ids)} "
        f"thread_context={len(thread_context_email_ids)} "
        f"primary_hits_with_attachments={len(primary_candidate_email_ids_with_attachments)} "
        f"attachment_extraction_called={bool(attachment_extraction_kwargs)}",
        flush=True,
    )

    lines = [
        "[RESUME_CANDIDATE_REVIEW_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'resume_candidate_review')}",
        f"days: {days}",
        f"execution_mode: {execution_mode}",
        f"mailbox_scope: {mailbox_scope}",
        f"search_query: {search_query or '(not run)'}",
        f"resume_keywords: {', '.join(RESUME_QUERY_TERMS)}",
        f"max_lookback_days: {MAX_LOOKBACK_DAYS}",
        f"search_max_results: {SEARCH_MAX_RESULTS}",
        f"matched_candidate_email_count: {len(matched_email_ids)}",
        f"primary_candidate_email_count: {len(primary_candidate_email_ids)}",
        f"thread_context_email_count: {len(thread_context_email_ids)}",
        f"attachment_checks_count: {len(attachment_check_results)}",
        f"matched_candidate_emails_with_attachments: {len(primary_candidate_email_ids_with_attachments)}",
        f"attachment_extraction_called: {bool(attachment_extraction_kwargs)}",
        "notes:",
        "- The default recent-scan lookback window is capped at 7 days.",
        "- resume_candidate_review now prefers explicit targets from email_ids, query, candidate_names, or prior read_results before falling back to recent inbox scanning.",
        "- search_emails scans for candidate, applicant, application, resume, CV, portfolio, and related English resume-review signals.",
        "- get_email_attachments is called for every matched or targeted candidate email to determine whether the candidate message includes attached files.",
        "- Sent or reply emails may be retained as thread context, but they should not be treated as new standalone candidate hits when they belong to the same candidate thread.",
        "- If at least one primary candidate email includes attachments and a usable query is available, extract_recent_attachment_texts is called and the relevant attachment text sections below are passed directly to the external finalizer LLM.",
        "- Finalizer instruction: produce a structured candidate summary for each primary candidate email, grounded first in extracted attachment text when available, and treat thread-context emails only as progress notes for the associated candidate.",
        "- Finalizer instruction: if a search hit, attachment, or extracted attachment text is not actually a resume, CV, candidate profile, job application, cover letter, or other genuine hiring material, ignore it completely and do not show it to the user.",
        "- For each candidate, include candidate identity if available, likely role or position, attachment evidence, key background or skills stated in the attachment text, limitations or missing evidence, thread progress if any, and a recommended next step.",
        "- If attachment text is missing or extraction failed, explicitly say that the summary is limited and rely only on the search hit and attachment listing evidence.",
        "- Do not invent qualifications, years of experience, or role fit that are not supported by the search results, attachment listings, or extracted attachment text below.",
        "",
        "[SEARCH_EMAILS]",
        "tool: search_emails",
        f"arguments: {search_kwargs if search_kwargs is not None else '(not run)'}",
        search_text or "(not run)",
        "",
        "[MATCHED_CANDIDATE_EMAIL_IDS]",
        _format_email_id_list(matched_email_ids),
        "",
        "[PRIMARY_CANDIDATE_EMAIL_IDS]",
        _format_email_id_list(primary_candidate_email_ids),
        "",
        "[THREAD_CONTEXT_EMAIL_IDS]",
        _format_email_id_list(thread_context_email_ids),
        "",
        "[ATTACHMENT_CHECK_RESULTS]",
        f"count: {len(attachment_check_results)}",
    ]

    if not attachment_check_results:
        lines.append("(no candidate-like emails were returned or recovered)")
    else:
        for index, attachment_result in enumerate(attachment_check_results, start=1):
            lines.extend(
                [
                    "",
                    f"[EMAIL_ATTACHMENTS_{index}]",
                    "tool: get_email_attachments",
                    f"email_id: {attachment_result['email_id']}",
                    f"arguments: {attachment_result['kwargs']}",
                    f"has_attachments: {attachment_result['has_attachments']}",
                    attachment_result["text"],
                ]
            )

    lines.extend(
        [
            "",
            "[MATCHED_PRIMARY_CANDIDATE_EMAIL_IDS_WITH_ATTACHMENTS]",
            _format_email_id_list(primary_candidate_email_ids_with_attachments),
        ]
    )

    if thread_context_email_ids:
        lines.extend(
            [
                "",
                "[THREAD_CONTEXT_NOTES]",
                "These email ids were treated as follow-up or thread-context messages rather than standalone candidate hits:",
                _format_email_id_list(thread_context_email_ids),
            ]
        )

    if attachment_extraction_kwargs is not None:
        lines.extend(
            [
                "",
                "[ATTACHMENT_EXTRACTION_CALL]",
                "tool: extract_recent_attachment_texts",
                f"arguments: {attachment_extraction_kwargs}",
            ]
        )
        if filtered_attachment_extraction_text:
            lines.extend(["", filtered_attachment_extraction_text])
        else:
            lines.extend(
                [
                    "",
                    "[RELEVANT_ATTACHMENT_TEXT_EXTRACTIONS]",
                    "(attachment extraction ran, but no relevant message-id sections were recovered for the matched primary candidate emails)",
                ]
            )
    else:
        explanation = (
            "(attachment extraction was not called because no primary candidate email with attachments was found)"
            if not primary_candidate_email_ids_with_attachments
            else "(attachment extraction was not called because no usable query could be derived for the targeted primary candidate emails)"
        )
        lines.extend(
            [
                "",
                "[RELEVANT_ATTACHMENT_TEXT_EXTRACTIONS]",
                explanation,
            ]
        )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": (
            f"Collected {len(primary_candidate_email_ids)} primary candidate email(s), "
            f"tracked {len(thread_context_email_ids)} thread-context email(s), "
            f"and passed through relevant extracted attachment text for {len(primary_candidate_email_ids_with_attachments)} primary candidate email(s) with attachments."
        ),
    }
