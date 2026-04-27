# Gmail Provider

## Purpose

The Gmail branch wires Gmail email tools, Google Calendar, attachment extraction, unsubscribe tools, and provider-specific plugins into the agent runtime.

## Main Components

- `GmailCompat`: Gmail tool class with OpenAI-compatible method annotations.
- `GoogleCalendar`: calendar tool provider.
- `calendar_approval_plugin`: approval gate for calendar writes.
- `gmail_sync_plugin`: post-send CRM synchronization.
- `extract_recent_attachment_texts`: attachment text extraction.
- `get_unsubscribe_info` and `post_one_click_unsubscribe`: unsubscribe support.

## Activation

The branch is enabled when Gmail is explicitly linked or when Gmail credentials are detected outside test and CI environments.

## Notes

Gmail is the most complete provider path in the current solution. Some features, especially unsubscribe and CRM sync, are Gmail-only today.
