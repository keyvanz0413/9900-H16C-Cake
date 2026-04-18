from __future__ import annotations

import re
from typing import Any, Callable


SEARCH_MAX_RESULTS = 350
MAX_LOOKBACK_DAYS = 7
EMAIL_ID_PATTERN = re.compile(r"^\s*ID:\s*(\S+)\s*$", re.MULTILINE)
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


def _call_tool(name: str, tool_callable: Callable[..., Any], kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], str]:
    print(f"[skill:resume_candidate_review] calling {name} with {kwargs}", flush=True)
    try:
        result = tool_callable(**kwargs)
    except Exception as exc:
        result = f"Error: {exc}"
    text = str(result or "").strip() or "(empty)"
    print(f"[skill:resume_candidate_review] finished {name}", flush=True)
    return name, kwargs, text


def _build_resume_query(days: int) -> str:
    return f"in:inbox newer_than:{days}d ({' OR '.join(RESUME_QUERY_TERMS)})"


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


def execute_skill(*, arguments, used_tools, skill_spec):
    raw_days = arguments.get("days", 7)
    days = int(raw_days)
    if days < 1:
        days = 1
    if days > MAX_LOOKBACK_DAYS:
        days = MAX_LOOKBACK_DAYS

    search_query = _build_resume_query(days)
    print(f"[skill:resume_candidate_review] start days={days}", flush=True)

    _, search_kwargs, search_text = _call_tool(
        "search_emails",
        used_tools["search_emails"],
        {"query": search_query, "max_results": SEARCH_MAX_RESULTS},
    )

    matched_email_ids = _extract_email_ids(search_text)
    attachment_check_results: list[dict[str, Any]] = []
    matched_email_ids_with_attachments: list[str] = []
    for email_id in matched_email_ids:
        _, attachment_kwargs, attachment_text = _call_tool(
            "get_email_attachments",
            used_tools["get_email_attachments"],
            {"email_id": email_id},
        )
        has_attachments = _attachment_list_has_files(attachment_text)
        if has_attachments:
            matched_email_ids_with_attachments.append(email_id)
        attachment_check_results.append(
            {
                "email_id": email_id,
                "kwargs": attachment_kwargs,
                "text": attachment_text,
                "has_attachments": has_attachments,
            }
        )

    attachment_extraction_kwargs: dict[str, Any] | None = None
    attachment_extraction_text = ""
    filtered_attachment_extraction_text = ""
    if matched_email_ids_with_attachments:
        attachment_extraction_query = f"{search_query} has:attachment"
        _, attachment_extraction_kwargs, attachment_extraction_text = _call_tool(
            "extract_recent_attachment_texts",
            used_tools["extract_recent_attachment_texts"],
            {"query": attachment_extraction_query, "max_results": SEARCH_MAX_RESULTS},
        )
        filtered_attachment_extraction_text = _extract_relevant_attachment_text_sections(
            attachment_extraction_text,
            relevant_message_ids=matched_email_ids_with_attachments,
        )

    print(
        "[skill:resume_candidate_review] collected "
        f"search_matches={len(matched_email_ids)} "
        f"attachment_checks={len(attachment_check_results)} "
        f"candidate_emails_with_attachments={len(matched_email_ids_with_attachments)} "
        f"attachment_extraction_called={bool(attachment_extraction_kwargs)}",
        flush=True,
    )

    lines = [
        "[RESUME_CANDIDATE_REVIEW_BUNDLE]",
        f"skill_name: {skill_spec.get('name', 'resume_candidate_review')}",
        f"days: {days}",
        f"search_query: {search_query}",
        f"resume_keywords: {', '.join(RESUME_QUERY_TERMS)}",
        f"max_lookback_days: {MAX_LOOKBACK_DAYS}",
        f"search_max_results: {SEARCH_MAX_RESULTS}",
        f"matched_candidate_email_count: {len(matched_email_ids)}",
        f"attachment_checks_count: {len(attachment_check_results)}",
        f"matched_candidate_emails_with_attachments: {len(matched_email_ids_with_attachments)}",
        f"attachment_extraction_called: {bool(attachment_extraction_kwargs)}",
        "notes:",
        "- The lookback window is capped at 7 days.",
        "- search_emails scans the inbox for candidate, applicant, application, resume, CV, portfolio, and related English resume-review signals.",
        "- get_email_attachments is called for every matched candidate email to determine whether the candidate message includes attached files.",
        "- If at least one matched candidate email includes attachments, extract_recent_attachment_texts is called and the relevant attachment text sections below are passed directly to the external finalizer LLM.",
        "- Finalizer instruction: produce a structured candidate summary for each relevant candidate email, grounded first in extracted attachment text when available.",
        "- Finalizer instruction: if a search hit, attachment, or extracted attachment text is not actually a resume, CV, candidate profile, job application, cover letter, or other genuine hiring material, ignore it completely and do not show it to the user.",
        "- For each candidate, include candidate identity if available, likely role or position, attachment evidence, key background or skills stated in the attachment text, limitations or missing evidence, and a recommended next step.",
        "- If attachment text is missing or extraction failed, explicitly say that the summary is limited and rely only on the search hit and attachment listing evidence.",
        "- Do not invent qualifications, years of experience, or role fit that are not supported by the search results, attachment listings, or extracted attachment text below.",
        "",
        "[SEARCH_EMAILS]",
        "tool: search_emails",
        f"arguments: {search_kwargs}",
        search_text,
        "",
        "[MATCHED_CANDIDATE_EMAIL_IDS]",
        ", ".join(matched_email_ids) if matched_email_ids else "(none)",
        "",
        "[ATTACHMENT_CHECK_RESULTS]",
        f"count: {len(attachment_check_results)}",
    ]

    if not attachment_check_results:
        lines.append("(no candidate-like emails were returned by search_emails)")
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
            "[MATCHED_CANDIDATE_EMAIL_IDS_WITH_ATTACHMENTS]",
            ", ".join(matched_email_ids_with_attachments) if matched_email_ids_with_attachments else "(none)",
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
                    "(attachment extraction ran, but no relevant message-id sections were recovered for the matched candidate emails)",
                ]
            )
    else:
        lines.extend(
            [
                "",
                "[RELEVANT_ATTACHMENT_TEXT_EXTRACTIONS]",
                "(attachment extraction was not called because none of the matched candidate emails had attachments)",
            ]
        )

    return {
        "completed": True,
        "response": "\n".join(lines).strip(),
        "reason": (
            f"Collected candidate-related search hits, checked attachments for {len(matched_email_ids)} matched email(s), "
            f"and passed through relevant extracted attachment text for {len(matched_email_ids_with_attachments)} attachment-bearing candidate email(s)."
        ),
    }
