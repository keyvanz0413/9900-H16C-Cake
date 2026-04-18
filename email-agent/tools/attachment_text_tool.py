from __future__ import annotations

import base64
import html
import io
import re
import zipfile
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree

try:
    from pypdf import PdfReader
    from pypdf.errors import FileNotDecryptedError
except Exception:  # pragma: no cover - exercised when dependency is absent at runtime
    PdfReader = None

    class FileNotDecryptedError(Exception):
        """Fallback error type when pypdf is unavailable."""


_ATTACHMENT_TEXT_LIMIT = 4000
_SUPPORTED_EXTENSIONS = (".txt", ".md", ".html", ".pdf", ".docx")
_SUPPORTED_MIME_TYPES = (
    "text/plain",
    "text/markdown",
    "text/html",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
)
_ENCRYPTED_PDF_MESSAGE = "[Encrypted PDF attachment: unable to extract text.]"
_PDF_DEPENDENCY_MESSAGE = "[PDF extraction unavailable: pypdf is not installed.]"
_UNSUPPORTED_MESSAGE = "skipped (unsupported attachment type)"
_EMPTY_CONTENT_MESSAGE = "skipped (empty attachment content)"
_HREF_PATTERN = re.compile(r'href=["\']([^"\']+)["\']', flags=re.IGNORECASE)
_SCRIPT_STYLE_PATTERN = re.compile(
    r"<(script|style)\b[^>]*>.*?</\1>",
    flags=re.IGNORECASE | re.DOTALL,
)
_TAG_PATTERN = re.compile(r"<[^>]+>")


def _decode_attachment_bytes(raw_data: object) -> bytes:
    data = str(raw_data or "").strip()
    if not data:
        return b""
    padding = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + padding)
    except Exception:
        return b""


def _strip_html(text: str) -> str:
    normalized = str(text or "")
    if not normalized:
        return ""
    normalized = _SCRIPT_STYLE_PATTERN.sub(" ", normalized)
    normalized = normalized.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    normalized = normalized.replace("</p>", "\n").replace("</div>", "\n").replace("</li>", "\n")
    normalized = _TAG_PATTERN.sub(" ", normalized)
    normalized = html.unescape(normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    normalized = re.sub(r"\n\s*\n+", "\n\n", normalized)
    return normalized.strip()


def _extract_pdf_text(content: bytes) -> str:
    if not content:
        return ""
    if PdfReader is None:
        return _PDF_DEPENDENCY_MESSAGE
    try:
        reader = PdfReader(io.BytesIO(content))
    except Exception:
        return ""

    pages: list[str] = []
    try:
        page_slice = reader.pages[:8]
    except FileNotDecryptedError:
        return _ENCRYPTED_PDF_MESSAGE
    except Exception:
        return ""

    for page in page_slice:
        try:
            text = str(page.extract_text() or "").strip()
        except FileNotDecryptedError:
            return _ENCRYPTED_PDF_MESSAGE
        except Exception:
            text = ""
        if text:
            pages.append(text)
        if sum(len(chunk) for chunk in pages) >= _ATTACHMENT_TEXT_LIMIT:
            break

    return "\n".join(pages)[:_ATTACHMENT_TEXT_LIMIT].strip()


def _extract_docx_text(content: bytes) -> str:
    if not content:
        return ""
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            document_xml = archive.read("word/document.xml")
    except Exception:
        return ""
    try:
        root = ElementTree.fromstring(document_xml)
    except ElementTree.ParseError:
        return ""

    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            paragraphs.append(text)
        if sum(len(chunk) for chunk in paragraphs) >= _ATTACHMENT_TEXT_LIMIT:
            break

    return "\n".join(paragraphs)[:_ATTACHMENT_TEXT_LIMIT].strip()


def _extract_attachment_text(*, filename: str, mime_type: str, content: bytes) -> str:
    lowered_name = str(filename or "").strip().lower()
    lowered_type = str(mime_type or "").strip().lower()
    if not content:
        return ""
    if lowered_type in {"text/plain", "text/markdown"} or lowered_name.endswith((".txt", ".md")):
        return content.decode("utf-8", errors="replace")[:_ATTACHMENT_TEXT_LIMIT].strip()
    if lowered_type == "text/html" or lowered_name.endswith(".html"):
        return _strip_html(content.decode("utf-8", errors="replace"))[:_ATTACHMENT_TEXT_LIMIT].strip()
    if lowered_type == "application/pdf" or lowered_name.endswith(".pdf"):
        return _extract_pdf_text(content)
    if (
        lowered_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or lowered_name.endswith(".docx")
    ):
        return _extract_docx_text(content)
    return ""


def _is_supported_attachment(*, filename: str, mime_type: str) -> bool:
    lowered_name = str(filename or "").strip().lower()
    lowered_type = str(mime_type or "").strip().lower()
    return lowered_type in _SUPPORTED_MIME_TYPES or lowered_name.endswith(_SUPPORTED_EXTENSIONS)


def _header_value(message: dict[str, Any], header_name: str) -> str:
    payload = message.get("payload", {}) or {}
    headers = payload.get("headers", []) if isinstance(payload, dict) else []
    for header in headers:
        if not isinstance(header, dict):
            continue
        if str(header.get("name") or "").strip().lower() == header_name.lower():
            return str(header.get("value") or "").strip()
    return ""


def _display_date(message: dict[str, Any]) -> str:
    header_date = _header_value(message, "Date")
    if header_date:
        return header_date
    internal_date = str(message.get("internalDate") or "").strip()
    if not internal_date:
        return ""
    try:
        timestamp = int(internal_date) / 1000
        return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
    except Exception:
        return internal_date


def _fetch_attachment_bytes(service: Any, *, message_id: str, attachment_id: str) -> bytes:
    try:
        attachment_payload = (
            service.users()
            .messages()
            .attachments()
            .get(userId="me", messageId=message_id, id=attachment_id)
            .execute()
        )
    except Exception:
        return b""
    if not isinstance(attachment_payload, dict):
        return b""
    return _decode_attachment_bytes(attachment_payload.get("data"))


def _collect_attachments(service: Any, *, message: dict[str, Any]) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    message_id = str(message.get("id") or "").strip()

    def _visit(part: dict[str, Any]) -> None:
        filename = str(part.get("filename") or "").strip()
        mime_type = str(part.get("mimeType") or "").strip()
        body = part.get("body", {}) or {}
        attachment_id = str(body.get("attachmentId") or "").strip() if isinstance(body, dict) else ""
        inline_data = body.get("data") if isinstance(body, dict) else None

        if filename:
            supported = _is_supported_attachment(filename=filename, mime_type=mime_type)
            content = _decode_attachment_bytes(inline_data)
            if not content and attachment_id:
                content = _fetch_attachment_bytes(service, message_id=message_id, attachment_id=attachment_id)

            extracted_text = _extract_attachment_text(
                filename=filename,
                mime_type=mime_type,
                content=content,
            ) if supported else ""

            status = "extracted"
            if not supported:
                status = _UNSUPPORTED_MESSAGE
            elif not content:
                status = _EMPTY_CONTENT_MESSAGE
            elif not extracted_text:
                status = "skipped (extractable attachment but no text was recovered)"

            attachments.append(
                {
                    "filename": filename,
                    "mime_type": mime_type or "(unknown)",
                    "attachment_id": attachment_id or "(inline-data)",
                    "status": status,
                    "text": extracted_text,
                }
            )

        for child in part.get("parts", []) or []:
            if isinstance(child, dict):
                _visit(child)

    payload = message.get("payload", {}) or {}
    if isinstance(payload, dict):
        _visit(payload)
    return attachments


def extract_recent_attachment_texts_from_email_tool(
    *,
    email_tool: Any,
    days: int = 7,
    max_results: int = 10,
) -> str:
    safe_days = max(int(days or 0), 1)
    safe_max_results = min(max(int(max_results or 0), 1), 100)
    service = email_tool._get_service()
    query = f"in:inbox newer_than:{safe_days}d has:attachment"

    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=safe_max_results,
    ).execute()

    message_refs = results.get("messages", []) or []
    if not message_refs:
        return (
            f"No attachment-bearing inbox emails found in the last {safe_days} day(s).\n"
            f"Query: {query}"
        )

    lines = [
        f"Recent attachment text extraction for the last {safe_days} day(s).",
        f"Query: {query}",
        f"Message scan limit: {safe_max_results}",
        f"Matched message count: {len(message_refs)}",
        f"Supported attachment types: {', '.join(_SUPPORTED_EXTENSIONS)}",
        "",
    ]

    total_attachments = 0
    total_extracted = 0

    for index, message_ref in enumerate(message_refs, start=1):
        message_id = str(message_ref.get("id") or "").strip()
        if not message_id:
            continue

        message = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full",
        ).execute()
        attachments = _collect_attachments(service, message=message)
        total_attachments += len(attachments)
        total_extracted += sum(1 for item in attachments if item.get("status") == "extracted")

        lines.extend(
            [
                f"[EMAIL_{index}]",
                f"Message ID: {message_id}",
                f"Thread ID: {str(message.get('threadId') or '').strip() or '(unknown)'}",
                f"From: {_header_value(message, 'From') or '(unknown)'}",
                f"Subject: {_header_value(message, 'Subject') or '(no subject)'}",
                f"Date: {_display_date(message) or '(unknown)'}",
                f"Attachment count: {len(attachments)}",
            ]
        )

        if not attachments:
            lines.extend(["Attachments: none recoverable from payload", ""])
            continue

        for attachment_index, attachment in enumerate(attachments, start=1):
            lines.extend(
                [
                    f"[ATTACHMENT_{index}_{attachment_index}]",
                    f"Filename: {attachment['filename']}",
                    f"MIME Type: {attachment['mime_type']}",
                    f"Attachment ID: {attachment['attachment_id']}",
                    f"Status: {attachment['status']}",
                ]
            )
            if attachment["text"]:
                lines.extend(
                    [
                        "Extracted Text:",
                        attachment["text"],
                    ]
                )
            lines.append("")

    lines.insert(4, f"Attachment count: {total_attachments}")
    lines.insert(5, f"Extracted attachment count: {total_extracted}")
    return "\n".join(lines).strip()

