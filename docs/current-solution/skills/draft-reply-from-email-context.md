# Draft Reply From Email Context Skill

## Purpose

`draft_reply_from_email_context` locates a target email and packages its metadata, body, and writing-style profile for the finalizer. The skill drafts context only; it does not send mail or save a draft.

## Target Selection Modes

- `unanswered_rank`: inspect unanswered emails and choose by rank.
- `search_query`: search for a user-described email and use the first matching result.

The resolver should default to `unanswered_rank` with `target_rank=1` when the target is unclear.

## Writing Style

The skill reads `WRITING_STYLE.md` from runtime paths or the repository fallback. Missing style content is represented as an explicit placeholder.

## Finalizer Expectations

Produce a complete reply draft with recipient, subject, and body. State that it is a draft and has not been sent. Use only facts from the target email and the provided writing-style profile.

## Common Follow-Up

The planner may add `send_prepared_email` only when the user explicitly asks to send the prepared reply.
