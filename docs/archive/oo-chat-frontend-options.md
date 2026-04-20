# oo-chat integration analysis

## Premises and hard constraints

This analysis assumes **no changes to `oo-chat` connection-related code**. That code mainly includes `oo-chat/hooks/use-identity.ts`, `oo-chat/hooks/use-agent-info.ts`, `oo-chat/components/chat/use-agent-sdk.ts`, and `oo-chat/app/api/auth/route.ts`. That implies three direct constraints: first, the `oo-chat` home, session, and settings pages all go through the OpenOnion identity and token flow, so that dependency cannot be silently removed; second, the main chat path is not REST calls from this project’s `frontend`, but the `connectonion/react` agent address + session model; third, existing `backend/app/main.py` exposes `/agent/chat`, `/agent/chat/stream`, and similar REST/SSE endpoints, which do not match what `oo-chat` expects.

## Option 1: Keep backend, add a ConnectOnion-compatible bridge

Goal: do not touch `oo-chat`, while making `backend` look like an agent service `oo-chat` can connect to directly. Main changes:

- `backend/app/main.py`: add or mount a ConnectOnion-compatible entry that covers agent info, message input, session continuation, and health checks at minimum.
- `backend/app/services/agent/email_agent_client.py`: bridge adapters mapping `oo-chat` prompt, session, and approval state to existing `conversation_id`, `draft_action`, and `draft_session`.
- A new session mapping service: persist `oo-chat session_id -> backend conversation_id/draft_session`, or refresh, reconnect, and follow-up sends lose state.
- Event translation: backend today emits `start/status/review/draft_session/delta/done/error`, while `oo-chat` UI leans toward `tool_call`, `approval_needed`, `ask_user`; protocol translation is required.
- Project wiring: update `docker-compose.yml`, `Makefile`, README, and tests so the former `frontend` switches to `oo-chat` and local startup still works.

Strengths: maximizes reuse of backend services, data structures, tests, and send-confirmation logic; easier rollback during migration. Suggested risk score: `0.48`. Main risks: protocol mismatch makes the bridge a new complexity center; dual session state can drift, especially around draft confirmation and send; uncertainty whether `oo-chat` approval/interaction UI can fully mirror backend draft review; OpenOnion identity flow remains, widening system boundaries. Overall, this fits “replace frontend first, then tighten architecture.”

## Option 2: Retire backend, fold capabilities into agents/email-agent

Goal: make `agents/email-agent` the backend for `oo-chat` directly. Protocol fit is better because `agents/email-agent/main.py` already uses `host(agent, trust="strict")` with the ConnectOnion agent model. Main changes:

- `agents/email-agent/runtime/agent_runtime.py`: expand the chat-only runtime to cover preferences, state, confirmed send, calendar summaries, and related behavior.
- `agents/email-agent/runtime/runtime_state.py`: unify data directories, environment variables, and provider startup to absorb former backend runtime configuration.
- Backend modules tied to business state must move or be rewritten: preferences, draft sessions, pending actions, dashboard state, calendar state.
- If deployment still needs health, ready, and debug endpoints, add management surfaces on the agent side so operations do not lose observability when backend is removed.
- Again update `docker-compose.yml`, `Makefile`, and test layout so the system becomes a two-layer “oo-chat + email-agent” stack instead of three layers.

Strengths: protocol aligns with `oo-chat`, less middle adaptation, cleaner long-term structure. Suggested risk score: `0.72`. Risks: backend responsibilities are large; folding them into the agent concentrates protocol, business, state, monitoring, and provider lifecycle in one place; existing REST capabilities and test boundaries fragment, raising regression risk during refactor; if provider or agent init fails, frontend availability suffers; removing backend does not remove `oo-chat`’s OpenOnion dependency.

## Conclusion

If the goal is to land `oo-chat` as the project frontend quickly while keeping the current backend and rollback room, prefer Option 1. If the goal is a longer-term agent-first architecture and you accept a larger refactor, Option 2 is worth it. Given the current repo, Option 1 first, then reassess stability before converging toward Option 2.
