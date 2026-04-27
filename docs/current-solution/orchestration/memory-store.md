# Memory Store

## Purpose

The memory store owns read and write access to the Markdown memory files used by the current agent runtime.

## Files

- `email-agent/USER_PROFILE.md`
- `email-agent/USER_HABITS.md`
- `email-agent/WRITING_STYLE.md`

## Read Path

Runtime prompts and skills read memory files directly through the configured path object. Missing files are treated as empty memory rather than fatal errors.

## Write Path

1. Intent and finalizer stages collect update notes.
2. `MarkdownMemoryStore.apply_update()` selects the correct writer agent.
3. The writer agent merges the update with existing Markdown.
4. The file is overwritten with the merged version.

## Safety Rules

- Do not invent user facts.
- Prefer stable preferences over one-off observations.
- Keep writing style separate from profile and habits.
- Treat user corrections as higher authority than inferred memory.
