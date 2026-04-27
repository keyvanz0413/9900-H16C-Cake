# Outlook Provider

## Purpose

The Outlook branch lets the agent run with Outlook email and Microsoft Calendar tools when Gmail is not active.

## Components

- `Outlook()` for email operations.
- `MicrosoftCalendar()` for calendar operations.

## Differences From Gmail

- Outlook uses folders and categories rather than Gmail labels.
- Outlook search syntax differs from Gmail query syntax.
- Gmail-only plugins such as CRM sync and unsubscribe support are not mounted.
- Attachment extraction for resume workflows is not yet equivalent to Gmail.

## Roadmap

Recommended future work:

1. Add CRM update support equivalent to Gmail `update_contact`.
2. Implement Microsoft Graph attachment text extraction.
3. Add unsubscribe-header parsing through Outlook APIs.
4. Extend calendar approval coverage to Microsoft Calendar write tools.

Until then, this document describes the current limited Outlook branch.
