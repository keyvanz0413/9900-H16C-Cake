# Chat API Route

## Purpose

`oo-chat/app/api/chat/route.ts` forwards chat messages from the Next.js frontend to the configured agent. It can also support direct LLM chat depending on runtime configuration.

## Responsibilities

- Read the active agent URL from request state or default environment variables.
- Forward user messages and previous session state.
- Return assistant messages, tool UI events, approval events, and updated session data.
- Optionally apply request signing when the agent requires authenticated calls.

## Session Handling

The frontend stores the latest agent `session` payload and sends it back on the next request. This allows the ConnectOnion agent runtime to continue multi-turn state without the frontend understanding the internals.

## Approval Events

Calendar approval events are passed through the same chat channel. The frontend renders approval UI and sends the result back as an approval response event.

## Boundaries

The route should not store Gmail or Outlook tokens. Email-provider credentials remain in the agent runtime.
