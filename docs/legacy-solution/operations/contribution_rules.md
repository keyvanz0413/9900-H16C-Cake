# Development and submission workflow

This document defines the minimum collaboration rules for this repository.

## Branch naming

Use a single format:

`type/short-description`

Examples:

- `feat/chat-stream`
- `fix/gmail-push-auth`
- `refactor/email-agent-runtime`
- `docs/memory-plan`

Recommended types:

- `feat`: new feature
- `fix`: bug fix
- `refactor`: refactor
- `docs`: documentation
- `test`: tests
- `chore`: miscellaneous maintenance

## Commit messages

Use a single format:

`type(scope): summary`

Examples:

- `feat(agent): add scheduled task service`
- `fix(sync): handle stale push history ids`
- `docs(memory): update secretary memory plan`

## Pull request rules

- Do not push feature work directly to `main`.
- Code changes should include tests or explain why tests cannot be added.
- When agent behavior changes, prefer to note:
  - whether prompts changed
  - whether tool boundaries changed
  - whether session / memory / action flow changed
- Before merge, do at least one self-check:
  - critical tests pass
  - docs and implementation are not obviously out of sync

## Documentation rules

- `docs/` should only keep documentation that remains valid.
- Finished plans with no ongoing maintenance value should be deleted or moved to archive.
- Prefer merging similar plans so one topic does not spawn multiple documents.
- Titles should point at current code, not abstract concepts.

## Extra requirements for agent-related changes

- High-risk actions must keep confirmation boundaries.
- New background tasks must have deduplication, state recording, and observable output.
- Memory-related changes should distinguish:
  - immediate factual writes
  - background curation
  - reminder triggers

## Minimum checks before merge

- `backend/tests`
- `agents/email-agent/tests -m "not real_api"`

If these two groups are not run, state the reason clearly in the PR or commit message.
