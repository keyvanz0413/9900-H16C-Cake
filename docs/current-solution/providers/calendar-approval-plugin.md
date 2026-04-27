# Calendar Approval Plugin

## Purpose

`calendar_approval_plugin` intercepts calendar write operations before execution and asks the user for approval.

## Intercepted Writes

Typical write tools include event creation, meeting creation, event updates, and event deletion. Read-only calendar tools are allowed through.

## Approval Channels

1. Frontend IO: send `approval_needed` and wait for an approval response.
2. CLI prompt: use an interactive terminal picker when available.
3. Headless fallback: allow execution when no approval channel exists.

## Rejection Modes

- `reject_hard`: set a stop signal for the current session.
- `reject_explain`: raise an error that instructs the agent to explain the attempted action and next steps.
- Other rejection values: stop automatic retry and ask the user first.

## Session Scope

Session-level approval can allow the same tool for the rest of the session. Approval state is not durable across agent restarts.

## Preview

The plugin builds a readable preview containing event title, time, attendees, location, description, or destructive-delete warnings depending on the tool.
