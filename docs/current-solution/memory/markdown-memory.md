# Markdown Memory

## Purpose

The current agent keeps long-lived user memory in Markdown files so the content remains inspectable and editable outside the runtime.

## Files

| File | Purpose | Writer |
|---|---|---|
| `email-agent/USER_PROFILE.md` | User identity, role, stable preferences, and durable facts. | `user_memory_writer_agent` |
| `email-agent/USER_HABITS.md` | Behavioral patterns such as timing, grouping, and workflow preferences. | `user_memory_writer_agent` |
| `email-agent/WRITING_STYLE.md` | Email tone, structure, signature habits, and phrasing. | `writing_style_writer_agent` |

## Writeback Flow

1. The intent layer extracts candidate memory updates from a user turn.
2. The finalizer can add or refine memory update notes.
3. `MarkdownMemoryStore.apply_update()` sends the update to the relevant writer agent.
4. The writer agent rewrites the Markdown file with merged content.

## Usage

Skills and agent prompts read these files to personalize behavior. `draft_reply_from_email_context` relies on `WRITING_STYLE.md` when producing reply drafts.

## Deployment Note

Mount these files in Docker or another persistent volume. Without persistence, user memory is lost when the container is rebuilt or replaced.
