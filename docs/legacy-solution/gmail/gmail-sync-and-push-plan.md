# Gmail Automatic Sync and Push Plan

This document merges the former “automatic sync plan” and “watch / push progress notes” into a single, still-valid description.

## Goals

Keep Gmail-related capabilities firmly in the backend system layer, not ad hoc via agent prompts.

Core goals:

- Continuously maintain inbox cache
- Support watch + Pub/Sub push
- Keep low-frequency reconcile
- Provide a stable data source for dashboard, reminders, summaries, and follow-up

## What Is Done

### 1. Background sync loop

In place:

- Gmail credential loading
- Full sync / partial sync
- Local `inbox_cache.json`
- Local `gmail_sync_state.json`

### 2. Watch renewal

In place:

- `watch` registration
- Renewal before expiry
- Reconcile backfill
- Fallback to ordinary scheduled sync when no topic is configured

### 3. Push webhook

In place:

- `POST /integrations/gmail/push`
- Pub/Sub envelope decoding
- Basic authentication
- Background queue to trigger sync
- Merging duplicate pushes

### 4. Dashboard integration

These states are already exposed via the backend:

- Sync status
- Sync phase / progress
- Watch status
- Auth status
- Unread / priority / daily summary
- Reminders
- Notifications from scheduled tasks

### 5. Dashboard manual sync

The dashboard `Last Sync` can trigger Gmail sync manually.

Current behavior:

- `POST /dashboard/status/sync`
- Prefers incremental sync by default
- Falls back to full sync only when there is no local `last_history_id` or the history cursor is invalid
- `lastSyncAt` is completion time, not start time

Implications:

- First mailbox connection or invalid cursor can make manual sync slow
- Normal `Last Sync` clicks are usually fast when Gmail has few changes

### 6. Dashboard progress and browser debug logs

`GET /dashboard/status` also returns:

- `syncPhase`
- `syncStartedAt`
- `syncProgressCurrent`
- `syncProgressTotal`
- `lastSyncAt`

When `NEXT_PUBLIC_DEBUG_LOGS=true`, the frontend logs concise debug lines:

- `dashboard.sync.started`
- `dashboard.sync.phase`
- `dashboard.sync.progress`
- `dashboard.sync.done`
- `dashboard.sync.failed`

These help determine:

- Which sync phase is stuck
- Whether behavior looks incremental or closer to full sync
- Whether triage has reached a completed state

## Primary Files Today

- `backend/app/services/gmail/gmail_sync_service.py`
- `backend/app/services/gmail/gmail_sync_store.py`
- `backend/app/services/gmail/gmail_cache.py`
- `backend/app/services/gmail/gmail_push_auth.py`
- `backend/app/services/common/dashboard_status.py`
- `backend/app/main.py`

## Current Boundaries

- Gmail sync is a backend service, not an agent prompt concern.
- Dashboard and reminders prefer reading local cache over live provider calls.
- The push webhook only authenticates, decodes, and queues; it does not run a heavy resync in the request.
- Watch mode still keeps low-frequency reconcile to avoid long-term drift.

## Observability Today

### 1. Light observability already present

- `gmail_sync_state.json` continuously records sync / auth / watch / progress
- Dashboard reads `syncStatus + syncPhase + progress` directly
- Backend logs key Gmail sync and triage refresh events
- Manual dashboard sync has browser console progress logs

### 2. Still missing

Later additions:

- Push failure statistics
- Watch renewal failure alerts
- Clearer dead-letter / retry records
- External monitoring integration

### 3. Outlook parity

This automatic sync and push stack is mainly Gmail-oriented.

Outlook still relies on existing live-read / adapter fallback and is not fully aligned.

### 4. Notification delivery integration

Sync and push already update local state stably, but changes are not fully wired into a unified notification delivery layer.

Next:

- `NotificationOutboxService`
- Per-user proactive notification policy

## Current Conclusion

Gmail logic should no longer be described as “part of agent tools.”

It is closer to:

**A stateful mailbox system layer inside the backend**

That is the right boundary for the current code.
