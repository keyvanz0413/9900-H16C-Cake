# Attachment Text Tool

## Purpose

`extract_recent_attachment_texts(query, max_results=10)` extracts text from recent Gmail attachments so skills such as resume review can inspect candidate materials.

## Supported Formats

| Extension | Handling |
|---|---|
| `.txt` | Decode plain text. |
| `.md` | Decode Markdown text. |
| `.html` | Strip scripts, styles, and tags into readable text. |
| `.pdf` | Use `pypdf.PdfReader` when available; encrypted PDFs return a placeholder. |
| `.docx` | Read the zipped Word XML content. |

Unsupported attachments are marked as skipped.

## Limits

Each attachment section is capped by `_ATTACHMENT_TEXT_LIMIT` to avoid overloading context.

## Error Handling

Extraction failures are reported per attachment. The overall tool should keep returning useful results for the remaining attachments.

## Provider Scope

This tool is currently injected only in the Gmail branch. Outlook needs an equivalent Microsoft Graph attachment reader before it can use the same flow.
