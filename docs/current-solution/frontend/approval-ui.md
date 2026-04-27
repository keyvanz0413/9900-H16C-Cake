# Approval UI

## Purpose

The approval UI renders calendar write approvals requested by `calendar_approval_plugin`. It gives the user a chance to approve, reject, or provide feedback before the agent creates, updates, or deletes calendar events.

## Trigger

The backend plugin sends an `approval_needed` event that includes the tool name, arguments, and a human-readable preview. The frontend displays that preview in the chat flow.

## Response Contract

The frontend returns an `APPROVAL_RESPONSE` with these fields:

| Field | Meaning |
|---|---|
| `approved` | `true` allows the tool call; `false` rejects it. |
| `scope` | Optional `session` value allows the same tool for the rest of the session. |
| `mode` | Rejection mode such as `reject_hard` or `reject_explain`. |
| `feedback` | Optional user text passed back to the agent. |

## Expected UX

- Show the concrete calendar change before asking for approval.
- Keep the decision attached to the relevant chat turn.
- Preserve enough state for reconnects when the backend checkpoint exists.
- Do not silently approve calendar writes in the frontend.
