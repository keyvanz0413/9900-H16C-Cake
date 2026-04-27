# Provider Switching

## Purpose

The same `email-agent` codebase supports Gmail and Outlook, but only one email provider is activated at runtime.

## Decision Logic

- Use `LINKED_GMAIL` when explicitly enabled.
- Use `LINKED_OUTLOOK` when explicitly enabled and Gmail is not active.
- Outside test and CI environments, infer provider availability from configured credentials.
- Disable provider tools by default in tests and CI.

## Priority

Gmail wins if both providers are configured. The Outlook branch is skipped in that case.

## Tool Differences

| Area | Gmail | Outlook |
|---|---|---|
| Email | `GmailCompat` | `Outlook()` |
| Calendar | `GoogleCalendar()` | `MicrosoftCalendar()` |
| Plugins | Gmail sync and calendar approval | None by default |
| Attachments | Text extraction injected | Not injected |
| Unsubscribe | One-click and mailto tools | Not injected |

## No Provider

If no provider is active, the agent can still start with non-email capabilities, but email tools are unavailable.
