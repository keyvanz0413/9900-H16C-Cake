# Writing Style Profile Skill

## Purpose

`writing_style_profile` creates or updates `email-agent/WRITING_STYLE.md` from the user sent-mail history.

## Runtime Dependency

The skill uses `skill_runtime.agents.writing_style_writer`. If that writer agent is unavailable, the skill should fail explicitly.

## Flow

1. Read the existing writing style file if present.
2. Fetch recent sent emails.
3. Ask the writer agent to produce a JSON payload with Markdown content, user summary, and reason.
4. Validate required fields.
5. Overwrite `WRITING_STYLE.md` and return a bundle.

## Finalizer Expectations

Tell the user whether the profile was created or updated and summarize the result. Do not print the entire Markdown file unless the user asks to see it.

## When To Use

Use only when the user explicitly asks to learn, refresh, or update their writing style. It should not be inserted automatically into unrelated plans.
