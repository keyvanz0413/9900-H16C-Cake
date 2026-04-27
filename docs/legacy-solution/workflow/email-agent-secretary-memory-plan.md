# EmailAI Secretary-Style Agent Plan

## Goals

Evolve EmailAI from a “passively responsive email assistant” toward a “single-user secretary for the owner.”

The core is not an omniscient memory brain, but three stable experiences:

- Know the user: communication habits, work rhythm, default preferences
- Get things done: connect inbox, meetings, tasks, and follow-up into one workflow
- Remind proactively: brief at the right time, meeting reminders, follow-up nudges

---

## Current State

The project already has a solid base:

- Short-term memory, long-term memory, and operational cache
- Structured data: contacts, tasks, projects, summaries
- Inbox cache, Gmail sync, dashboard status
- Safety boundaries: draft review, action confirmation

It still feels more like an “email agent” than “the boss’s secretary.”

Main gaps:

- Preference profile is still shallow
- Reminders are partial logic, not a full reminder system
- No real scheduled-task layer yet
- No unified notification delivery layer
- Follow-up and meeting prep are not yet proactive workflows

---

## Phase-One Changes Already Landed

This round shipped low-risk changes first:

### 1. Extended secretary-style preference profile

On top of `preferences.json`, added:

- `briefing_style`
- `proactive_mode`
- `meeting_reminder_minutes_before`
- `follow_up_reminders_enabled`
- `daily_briefing_enabled`
- `daily_briefing_time`

These are not a “knowledge base”; they are operating defaults for “how the secretary serves the boss.”

### 2. Broader memory extraction

The backend can extract some secretary preferences from explicit phrasing, e.g.:

- “Act like my secretary”
- “Brief me every morning at 8:30”
- “Remind me 15 minutes before meetings”
- “Turn on follow-up reminders”

### 3. Reminder foundation

A local reminder service derives reminders from:

- Upcoming meetings
- Open tasks with `due_at`

### 4. Backend and dashboard

Reminders are exposed via:

- `/reminders`
- Dashboard notifications

Note: this is still “derived reminders,” not “scheduled push.”

### 5. Memory event log and daily curation

Added:

- `memory_journal.json`
- `memory_profile.json`
- `MemoryCuratorService`

The system now:

- Writes high-value memory events inline in the main path
- Runs a daily `memory_curation` scheduled task to tidy events
- Produces a more stable profile and daily curation markdown

---

## How to Read the Architecture

Think of the secretary stack in five layers:

### 1. Workflow state layer

Holds current session and pending actions:

- `data/email_agent_sessions.json`
- `data/memory/short_term.json`

Answers “what this turn is doing.”

### 2. User habit layer

Stable owner preferences:

- `data/memory/preferences.json`
- `data/contacts.csv`

Answers “how this owner works, communicates, and who matters.”

### 3. Memory events and profile layer

Facts worth remembering and curated profile:

- `data/memory/memory_journal.json`
- `data/memory/memory_profile.json`
- `data/memory_curations/*.memory_curation.md`

Answers “how scattered behavior becomes long-term habit profile.”

### 4. Tasks and reminder facts layer

Actionable facts:

- `data/memory/tasks.json`
- `data/meetings.json`

Answers “what to track, which meetings to prep, what is due soon.”

### 5. Proactive service layer

Turns facts into reminders, briefs, notifications:

- Reminder service
- Dashboard status
- Background sync
- Future scheduled jobs / notification delivery

Answers “when the secretary should surface, and in what form.”

---

## How Memory Should Keep Updating

A simpler, safer boundary:

- Do not build a giant “every turn decides what to remember” memory agent
- Keep inline writes on the backend main path
- Add a once-daily `memory curator` for summarizing, deduplicating, merging, cleanup

In one sentence:

**Main path records facts; curator tidies.**

### 1. What the main path writes immediately

Write straight to the memory store when these happen—no waiting for daily curation:

- Explicit preferences
- User corrections to the agent
- Confirmed decisions
- Task start / completion
- Contact importance changes
- Reminder preferences, e.g. “remind me 30 minutes before meetings”

This layer prevents losing critical facts.

### 2. What `memory curator` does daily

The curator does not own all memory—only background tidying.

Run it once per day, e.g. evening.

It reads:

- That day’s memory events
- Current stable preferences
- Recent daily summaries
- Recent conversation summaries
- Current open tasks / contacts

It outputs:

- Daily memory tidying summary
- Candidates to promote to long-term habits
- Duplicate memories to merge
- Old memories to demote or archive
- A cleaner user profile

### 3. Long-term memory bar

Not everything belongs in long-term memory.

Keep long-term only if:

- User explicitly said it
- Same behavior repeated 2–3 times
- The fact affects future agent behavior

One-off asks stay short-term only.

### 4. Recommended implementation boundary

To reduce risk, the curator should not freely rewrite every memory file.

Safer:

- Produce structured curation output first
- Backend applies updates by rule

So:

`event log -> curator -> structured patch -> memory store`

Even if the curator later becomes an LLM sub-agent, storage boundaries stay intact.

### 5. Suggested frequency

- Immediate: explicit preferences, corrections, confirmations, task state changes
- Daily: one full pass
- Optional: if the day is very busy, light extra passes every 10–20 meaningful messages

---

## Deliberately Not Touched Yet—What Next

These are the most critical pieces left out of production logic on purpose.

---

## 1. How scheduled tasks should work

### Goals

The system should not only “have reminder data,” but run fixed jobs at the right times.

Typical jobs:

- Morning owner brief
- Meeting brief at a fixed offset before start
- Follow-up reminder for long-unreply threads
- Evening rollup of unfinished work

### Existing foundation

The repo already has backend hooks:

- `DashboardStatusService.start_background_sync()`  
  [dashboard_status.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/common/dashboard_status.py)
- `GmailSyncService.start_background_loop()`  
  [gmail_sync_service.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/gmail/gmail_sync_service.py)
- Gmail push webhook  
  [main.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/main.py)

So “background threads + state files + push triggers” already exist.

### Recommended approach

Add a standalone `ScheduledTaskService`; do not put scheduling inside agent prompts.

Split responsibilities:

- Read schedule definitions
- Decide which jobs are due
- Write job run records
- Call the right system services
- Hand results to notification/outbox

Suggested new files:

- `backend/app/services/scheduling/scheduled_task_service.py`
- `backend/app/services/scheduling/scheduled_task_store.py`

Suggested local storage:

- `data/scheduled_tasks.json`
- `data/scheduled_task_runs.json`

Minimum task model fields:

- `task_id`
- `task_type`
- `enabled`
- `schedule_kind`
- `schedule_value`
- `payload`
- `last_run_at`
- `next_run_at`
- `last_status`

### Why not let the agent schedule itself first

Scheduling is a systems concern, not LLM reasoning.

If “when to run” is delegated to the agent:

- Unstable
- Hard to observe
- Hard to compensate failures
- Hard to guard against duplicate runs

Correct split:

- System decides when to run
- Agent decides how to generate content when run runs

### Recommended first batch

Only three at first:

1. `daily_briefing`
2. `meeting_brief`
3. `follow_up_digest`

Avoid too many types early—store and scheduler state will sprawl.

---

## 2. How notifications should work

### Goals

Not only show reminders on the dashboard, but proactively reach the owner.

### Current state

- Reminder derivation exists
- Dashboard notifications exist
- Email provider send exists

But no “notification delivery layer” yet.

### Recommended approach

Add `NotificationOutboxService` for all proactive notifications.

Suggested new files:

- `backend/app/services/notification_outbox_service.py`
- `backend/app/services/notification_policy.py`

Suggested local storage:

- `data/notification_outbox.json`

Minimum fields per notification:

- `notification_id`
- `kind`
- `channel`
- `title`
- `body`
- `scheduled_for`
- `status`
- `dedupe_key`
- `created_at`
- `sent_at`

### Why a separate outbox

Notifications are not “fire and forget”; they need:

- Deduplication
- Retry
- Throttling
- Failure records
- Audit

If every reminder hit sends email immediately:

- Easy to spam the user
- Hard to separate “reminder generated” vs “notification delivered”
- Hard to implement quiet hours, dedupe, batched send

Correct chain:

`fact -> reminder -> notification candidate -> outbox -> delivery`

### Recommended channel order

For this project stage:

1. Dashboard in-app notifications
2. Proactive brief inside agent chat
3. Email notifications
4. Later: browser push / mobile push

**Email notification is not step one, but should be among the first outbound channels.**

### How to send notification email

Do not reuse the normal user compose flow.

Add a dedicated “system notification email” path:

- Does not enter normal draft session
- Still subject to policy
- High-risk notifications may land in outbox only without auto-send

Start with notification types:

- Daily brief
- Morning digest
- Overdue follow-up digest

Avoid “one email per reminder”—too noisy.

Prefer digest-style notifications first.

---

## 3. How follow-up reminders should work

### Goals

A secretary reminds the owner not only before meetings, but about:

- Threads not yet replied to
- People waiting on confirmation
- Promises about to expire

### Current state

Reusable pieces exist:

- `DailySummaryService` detects reply-needed signals  
  [daily_summary_service.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/daily_summary_service.py)
- Dashboard priority inbox surfaces urgent / reply-needed tendencies  
  [dashboard_status.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/common/dashboard_status.py)

They are still “display logic,” not a formal follow-up engine.

### Recommended approach

Add `FollowUpService` to turn inbox cache into follow-up facts.

Responsibilities:

- Find threads likely waiting on the user
- Estimate wait duration
- Compare to user tolerance window
- Emit follow-up reminders or digest items

Suggested storage:

- `data/follow_up_state.json`

Minimum fields per follow-up fact:

- `thread_id`
- `subject`
- `from`
- `last_inbound_at`
- `last_outbound_at`
- `reply_expected`
- `priority`
- `reminder_state`

### Recommended rules

Rules first; do not let the agent judge freely yet:

- Important contacts
- No reply in last 24–72 hours
- Signals like confirm/reply/follow-up/gentle reminder in text
- Not bulk/newsletter

Stabilize recall first; then consider agent ranking or wording.

---

## 4. How meeting brief should work

### Goals

Before meetings, the secretary tells the owner:

- Whose meeting
- Why it matters
- What to prepare
- Recent email context

### Current state

- Local `meetings.json`
- Meeting schedule tools
- Email/cache context

No “pre-meeting briefing job” yet.

### Recommended approach

Add `MeetingBriefService`:

- Read upcoming meetings
- Pull related contacts and recent threads
- Produce structured briefing cards
- Surface on dashboard / outbox / chat

Do not auto-email external participants at first—serve the owner only.

---

## 5. New safety boundaries

If the system acts proactively, add:

### 1. Deduplication

Same meeting reminder or same overdue follow-up must not fire many times in a short window.

### 2. Quiet hours

Need quiet hours, e.g.:

- No routine reminders at night
- Weekends only high-priority reminders

### 3. Risk tiers

Low risk:

- Dashboard cards
- Local reminders

Medium risk:

- System notification email to the user

High risk:

- Sending on behalf of the user
- Auto-changing calendar or mailbox state

### 4. Revocable / traceable

Every proactive action should have a run record or outbox record for debugging.

---

## Recommended Rollout Order

### Phase 2

System scheduling, no auto outbound sends:

- `ScheduledTaskService`
- `scheduled_tasks.json`
- `scheduled_task_runs.json`
- `daily_briefing`
- `meeting_brief`
- `follow_up_digest`

### Phase 3

Notification delivery, narrow channels:

- `NotificationOutboxService`
- `notification_outbox.json`
- Dashboard + in-chat notifications
- Digest-style email notifications

### Phase 4

True secretary proactivity:

- Contact-specific preference
- Follow-up aging model
- Quiet hours
- Dedupe policy
- Notification policy
- Trust-gated auto actions

---

## One-Line Summary

The next priority is not “more memory,” but turning existing memory into runnable secretary workflows:

- Preferences
- Scheduled tasks
- Reminders
- Outbox
- Notification delivery
- Safety boundaries

Only then does the user move from “this agent remembers me” to:

**This agent really feels like it works for me.**
