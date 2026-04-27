# Follow-Up Service Plan

## Background

The current system already contains partial follow-up related logic, but it is still scattered across multiple places instead of being managed by one dedicated service.

At the moment:

- `shared/inbox_cache.py` already provides basic reply-needed heuristics such as:
  - `looks_like_reply_needed_message(...)`
  - `reply_needed_cached_messages(...)`
  - `estimate_reply_needed_messages(...)`
  - `is_bulk_like_message(...)`
- `backend/app/services/daily_summary_service.py` already generates simple follow-up hints for summaries.
- `backend/app/services/scheduling/scheduled_task_service.py` already contains `_run_follow_up_digest(...)`, which builds a follow-up digest directly from inbox messages.

This means the project already has the foundation for follow-up detection, but the logic is duplicated and embedded inside summary and scheduled-task flows. As the secretary-style agent evolves, follow-up should become a standalone reusable capability.

## Goal

The goal of this work is to introduce a dedicated `FollowUpService` that can:

- identify emails and threads that likely require a user reply
- calculate follow-up urgency and waiting time
- expose a unified list of follow-up candidates
- support scheduled follow-up digests
- support future dashboard, reminder, and notification integrations

This service should become the single source of truth for follow-up detection instead of keeping the logic spread across unrelated modules.

## Problem Statement

Without a dedicated follow-up service, the current implementation has several issues:

1. Follow-up detection is duplicated across multiple modules.
2. Different parts of the system may apply slightly different rules.
3. Scheduled tasks currently mix orchestration and business logic.
4. Future integrations such as dashboard, reminder, and notification delivery would need to reimplement similar filtering again.

To avoid these problems, the system should separate:

- **follow-up fact generation**
- **scheduled execution**
- **notification delivery**
- **UI presentation**

## Current Reusable Foundations

The following existing components can be reused.

### 1. Inbox cache heuristics

`shared/inbox_cache.py` already contains useful signal extraction logic, especially for:

- detecting whether a message looks like a reply-needed email
- filtering bulk-like messages
- estimating reply-needed candidates from cached inbox messages

This should be reused instead of rewriting the same logic.

### 2. Daily summary follow-up hinting

`backend/app/services/daily_summary_service.py` already contains lightweight follow-up hint generation.  
This shows that follow-up information is already useful to the product, but it is currently presentation-oriented instead of service-oriented.

### 3. Scheduled follow-up digest

`backend/app/services/scheduling/scheduled_task_service.py` already implements a basic follow-up digest runner.  
However, it directly performs candidate discovery itself. That logic should be moved into a dedicated service so scheduled tasks only orchestrate execution.

### 4. Email triage results

`backend/app/services/triage/email_triage_service.py` already provides priority and categorisation output that can later be combined with follow-up scoring.

## Proposed Design

## New Service

Add:

- `backend/app/services/workflow/follow_up_service.py`

Optional later additions:

- `backend/app/services/follow_up_store.py`
- `data/follow_up_state.json`

## Responsibilities of FollowUpService

`FollowUpService` should be responsible for:

- reading cached inbox messages
- identifying messages that likely require a user reply
- excluding bulk, newsletter, and low-value messages
- calculating age and urgency
- returning a unified list of follow-up candidates
- providing a reusable digest-friendly representation

It should **not** be responsible for:

- sending notifications
- mutating mailbox state
- sending replies
- UI formatting beyond simple digest-ready text preparation

In other words, the service should produce **follow-up facts**, not execute user-facing actions.

## High-Level Flow

1. Read cached inbox messages.
2. Filter out invalid or irrelevant items.
3. Exclude bulk/newsletter-like messages.
4. Apply reply-needed heuristics.
5. Enrich candidates with timing and priority metadata.
6. Return a sorted list of follow-up items.
7. Allow scheduled tasks and UI layers to consume the same result.

## Follow-Up Candidate Schema

The first version should use a simple structured item such as:

- `message_id`
- `thread_id`
- `subject`
- `from`
- `sender_email`
- `last_inbound_at`
- `last_outbound_at`
- `age_hours`
- `reply_expected`
- `priority`
- `reason_tags`
- `snippet`
- `reminder_state`

### Field Notes

- `message_id`: concrete message reference for display/debugging
- `thread_id`: used to group related follow-up items later
- `subject`: concise display title
- `from`: sender display text
- `sender_email`: sender email for future contact-based rules
- `last_inbound_at`: latest received timestamp from the other party
- `last_outbound_at`: optional, for future enhancement when sent-mail history is included
- `age_hours`: how long the user has been waiting to reply
- `reply_expected`: whether the system believes a reply is expected
- `priority`: `high`, `medium`, or `low`
- `reason_tags`: machine-readable explanation tags such as `reply_needed`, `confirm_request`, `important_contact`
- `snippet`: short context preview
- `reminder_state`: initially optional, for future reminder dedupe

## Phase 1 Heuristics

The first implementation should stay simple and rule-based.

### Include candidate if

A message should become a follow-up candidate when all or most of the following are true:

- it exists in inbox cache
- it is a valid message object
- it is not bulk-like
- it is within the configured time window
- it looks like a reply-needed message according to existing heuristics  
  **or**
- triage marks it as reply-needed in a future integration

### Exclude candidate if

A message should be excluded if:

- it is bulk-like or newsletter-like
- it is clearly automated system noise
- it is too old for the requested digest window
- it has insufficient sender/subject context
- it is obviously informational only

### Priority Rules

#### High priority

A candidate should be marked high when:

- it contains strong follow-up signals such as:
  - `please confirm`
  - `awaiting your reply`
  - `gentle reminder`
  - `second request`
  - `follow up`
- triage later marks it as a high-priority reply-needed item
- it comes from a likely important sender or direct contact

#### Medium priority

A candidate should be marked medium when:

- it passes reply-needed heuristics
- it is not bulk-like
- it does not contain strong urgency signals

#### Low priority

A candidate should be marked low when:

- it is only weakly suggestive of needing action
- it is recent but not clearly urgent
- it is useful to include in a longer follow-up list but not in top digest items

## Sorting Strategy

Candidates should be sorted primarily by:

1. priority
2. age in hours
3. recency of inbound timestamp

This makes the output more useful for both digest generation and future dashboard display.

## Initial Public API

The first version of `FollowUpService` should expose at least two methods:

### `list_candidates(window_hours=72, limit=20)`

Returns the structured follow-up items for system consumers such as dashboard, reminders, or future APIs.

### `build_digest_items(window_hours=72, limit=8)`

Returns simplified items or lines suitable for digest generation.

This separation keeps business logic in one place while allowing different consumers to request different output formats.

## Integration Plan

### Phase 1: Introduce FollowUpService

Create `follow_up_service.py` and implement:

- inbox cache loading
- candidate filtering
- basic priority classification
- candidate sorting
- structured output methods

At this stage, no persistent follow-up state is required.

### Phase 2: Refactor scheduled task flow

Update `backend/app/services/scheduling/scheduled_task_service.py` so that `_run_follow_up_digest(...)` no longer contains its own candidate-selection logic.

Instead, it should:

1. call `FollowUpService`
2. receive follow-up candidates
3. write digest output

This keeps scheduled tasks focused on orchestration.

### Phase 3: Dashboard integration

Expose follow-up candidates to dashboard-related views or APIs so the user can see unresolved reply-needed emails in one place.

### Phase 4: Reminder and notification integration

Later, connect follow-up output to:

- reminder generation
- notification outbox
- repeat reminder suppression
- user preference based scheduling

## Future Enhancements

The first version should stay simple. The following can be added later:

### 1. Follow-up state persistence

Add:

- `backend/app/services/follow_up_store.py`
- `data/follow_up_state.json`

This would allow the system to track:

- last reminded time
- reminder count
- reminder suppression state
- snoozed threads

### 2. Thread-level reasoning

Instead of treating messages independently, later versions can collapse messages into threads and determine whether the latest turn is from the other party and whether the user owes a response.

### 3. Contact-aware prioritisation

Combine follow-up detection with:

- contact repository
- memory profile
- sender importance
- user preferences

This would allow better ranking of supervisor/client/teammate emails.

### 4. Triage integration

Later versions should consume triage output directly so the follow-up module aligns with the system-wide priority funnel.

## Testing Plan

Add tests such as:

- non-bulk unread message becomes a candidate
- newsletter/bulk email is excluded
- messages containing strong follow-up wording become high priority
- old messages outside the window are excluded
- digest generation works when candidates exist
- digest generation returns empty output safely when no candidates exist

Suggested test file:

- `backend/tests/test_follow_up_service.py`

## Implementation Checklist

### Documentation
- [ ] Add `docs/workflow/follow-up-service-plan.md`

### Service
- [ ] Add `backend/app/services/workflow/follow_up_service.py`
- [ ] Implement `list_candidates(...)`
- [ ] Implement `build_digest_items(...)`

### Refactor
- [ ] Update `scheduled_task_service.py` to call `FollowUpService`
- [ ] Remove duplicated follow-up filtering from scheduled task logic

### Tests
- [ ] Add `backend/tests/test_follow_up_service.py`
- [ ] Add rule-based candidate coverage
- [ ] Add scheduled-task integration coverage

## Expected Outcome

After this work:

- follow-up detection will have a single reusable service
- scheduled tasks will stop duplicating business logic
- dashboard and future reminder flows can reuse the same output
- the system architecture will be cleaner and easier to extend

This will make follow-up a proper first-class secretary capability rather than a small helper embedded inside other modules.