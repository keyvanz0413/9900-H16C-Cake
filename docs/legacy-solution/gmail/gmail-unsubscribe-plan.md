# Gmail Unsubscribe Capability Plan

This document only reflects the unsubscribe capability boundaries that actually exist in the current code.

## Goals

Enable EmailAI to safely handle newsletter / mailing list cleanup while preserving:

- Auditability
- Explicit confirmation
- Batch operations
- No silent execution of high-risk actions

## What Already Exists

### 1. Unsubscribe candidate detection

The system can already identify from cached mail:

- `List-Unsubscribe`
- `List-Unsubscribe-Post`
- `mailto`
- Mailing list / sender grouping

### 2. Main agent tools

The main path already includes:

- `list_unsubscribe_candidates`
- `queue_unsubscribe_action`
- `queue_unsubscribe_matching_action`

### 3. Backend execution layer

The backend already supports these action types:

- `unsubscribe_email`
- `unsubscribe_one_click`
- `unsubscribe_mailto`
- `unsubscribe_open_website`

And they still follow:

`queue -> confirm -> execute`

### 4. Batch processing

For multiple mailing lists, the system already supports:

- Aggregating candidates first
- Requesting confirmation in one go
- Batch execution
- Optional archiving of existing mail

## Current Boundaries

- One-click and mailto can be executed automatically.
- Opening website links is low-automation; the system does not silently complete site interactions for the user by default.
- Unsubscribe actions remain mailbox actions and do not bypass the confirmation layer.

## Primary Files Today

- `agents/email-agent/runtime/mailbox_tools.py`
- `backend/app/services/agent/email_agent_client.py`
- `backend/app/services/agent/email_agent_client_actions.py`
- `backend/app/services/workflow/pending_action_executor.py`
- `shared/unsubscribe_parser.py`

## What Is Not Done Yet

### 1. Stronger default policies

The system can already record newsletter preferences, but “long-term default actions” have not been refined into finer-grained sender / list-level policies.

Possible follow-ups:

- Sender-level default behavior
- List-ID-level default behavior
- Post-unsubscribe auto-archive / mark-read policies

### 2. Finer risk tiers

Later, continue to subdivide by mechanism:

- One-click: lowest risk
- Mailto: low-to-medium risk
- Open website: semi-automatic only, no silent automation

### 3. Dashboard and notification integration

Unsubscribe outcomes, failure reasons, and flows that need human follow-up on the website can later be wired to the dashboard or notification outbox.

## Current Conclusion

Unsubscribe is no longer a “pure analysis proposal”; it is a shipped system capability.

The most important work now is not debating whether it can be done, but making clearer:

- Default policies
- Risk tiers
- Observability of results
