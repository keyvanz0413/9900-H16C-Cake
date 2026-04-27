# Email Agent Runtime Refactor and Follow-Ups

This document only reflects the refactor status of the backend-embedded email agent and remaining work.

## Refactor Goals

Stabilize the system around this boundary:

- Backend is the orchestration hub
- Runtime is the embedded reasoning layer
- Tools are trimmed per turn; the main agent does not keep the full capability set open forever
- Read paths are cache-first where possible
- Write paths are review-first / confirm-first

## Completed

### 1. Prompt aligned with real tools

- Provider prompts are aligned with actual bundle capabilities
- The backend injects for the current turn:
  - Routing
  - Currently available tools
  - Bundle playbook
  - Tool usage rules

### 2. Session state persistence

The following moved from pure in-memory to local persistence:

- Conversation history
- Draft session
- Action session

Corresponding file:

- `data/email_agent_sessions.json`

### 3. Bundle execution tightened

The main agent now prefers creating bundle-specific instances per request instead of mutating the globally shared `agent.tools`.

This makes concurrency on the main path much safer than before.

### 4. Provider tools and shared sub-agents locked

Style learning, review, weekly summary, contacts, and mailbox read/write paths have concurrency protection.

### 5. Gmail system layer strengthened

Integrated:

- Background sync loop
- Inbox cache
- Gmail watch
- Pub/Sub push webhook

These belong to backend services and are no longer driven by prompts alone.

### 6. Secretary-style memory and daily curation

Already in place:

- Preference profile extensions
- Reminder derivation
- Scheduled tasks
- Memory journal
- Daily memory curator

## Boundaries That Still Hold

- Mailbox actions still follow `queue -> confirm -> execute`
- Unsubscribe still uses explicit pending actions; no silent default execution
- The dashboard still prefers consuming backend service results, not direct agent reasoning

## Remaining Work

### 1. Remove legacy fallback

The backend still keeps a compatibility fallback for an old runtime.

Later, remove:

- Global bundle switch compatibility path
- Associated old locks and adapter branches

### 2. Notification delivery layer

The system can already produce:

- Daily briefing
- Meeting brief
- Follow-up digest
- Memory curation

But these mostly stay in local files and the dashboard.

Add later:

- `NotificationOutboxService`
- Deduplication policy
- Delivery status records

### 3. Memory confidence model

The memory curator is still a rule-based tidying layer.

Next steps:

- `confidence`
- `last_confirmed_at`
- `superseded_by`
- Contact-level behavioral preferences

### 4. Unified evaluation

Later, fold these into regular regression:

- Prompt / tool drift
- Session recovery
- Scheduled task deduplication
- Memory curation output
- Unsubscribe execution path

## Current Conclusion

This stack has moved from “one large prompt driving an all-capable agent” to:

**Strong backend orchestration, runtime split by bundle, local state persistence, and background jobs as first-class system behavior**

The next focus is not expanding prompts further, but tightening system boundaries and backend workflows.
