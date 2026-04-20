# Email Layered Triage Funnel Plan

This document unifies “email classification, urgency, and layered retrieval” into one implementation plan that fits this repository.

The core conclusion in one sentence:

**Use one unified funnel service to output both `category` and `priority` on the same pipeline.**

That supports category-wide retrieval, urgent/meeting/reply-needed detection, and avoids splitting the project into two redundant systems.

## Goals

Every message should end with two kinds of results:

### 1. Category

- `meeting`
- `reply_needed`
- `project_update`
- `finance`
- `security`
- `newsletter`
- `notification`
- `personal`
- `other`

### 2. Priority

- `P0_URGENT`
- `P1_ACTION_NEEDED`
- `P2_NORMAL`
- `P3_LOW_VALUE`

### 3. Extra fields

- `priority_score`
- `confidence`
- `reasons`
- `deadline_info`
- `suggested_action`

Unified structure:

```json
{
  "message_id": "msg_123",
  "thread_id": "thread_456",
  "category": "meeting",
  "priority_label": "P0_URGENT",
  "priority_score": 0.92,
  "confidence": 0.88,
  "reasons": [
    "meeting starts soon",
    "confirmation requested",
    "high-priority sender"
  ],
  "deadline_info": {
    "detected": true,
    "due_at": "2026-03-28T15:00:00+11:00",
    "hours_left": 1.5
  },
  "suggested_action": "prepare_meeting_brief"
}
```

## Why Only One Funnel

The project will need two query styles:

- By category:
  - Meeting mail
  - Finance mail
  - Newsletters
  - Reply-needed mail
- By priority:
  - Most urgent
  - Must handle today
  - Low-value cleanup

So a single-urgency-only system is not enough, and splitting category and priority into inconsistent services is worse.

Best boundary:

- **One funnel**
- **Two output heads**

Meaning:

`Same pipeline -> category + priority together`

## Storage Boundary

This project does not introduce a database.

Triage stays on local files already in use:

- `JSON`
  - Structured triage, feedback, rule config, cache
- `CSV`
  - Contacts, priority relationships, tabular data
- `MD`
  - Briefings, summaries, human-readable outputs

This plan does not design:

- PostgreSQL
- Kafka
- Vector database
- Standalone feature store

Target pipeline shape:

`inbox_cache.json -> email_triage_index.json -> briefing/reminder/dashboard`

## Mailbox Initialization and Bootstrap

On first connection, do not hand all mail to the agent first—run a local bootstrap.

Suggested fixed order:

1. Gmail / Outlook first sync writes recent mail to `inbox_cache.json`
2. `EmailTriageService` reads the cache and runs the unified funnel in batch
3. Results go to `email_triage_index.json`
4. Dashboard, daily summary, reminders, follow-up digest read the triage index first

The goal is not “deep understanding of all history,” but organizing recent mail into:

- Category-indexable
- Priority-sortable
- Incremental sync can refresh triage index

Suggested bootstrap states:

- `not_started`
- `bootstrapping`
- `ready`
- `degraded`

The actual pipeline should be:

`gmail_sync_service -> gmail_cache -> EmailTriageService.refresh_index() -> email_triage_index.json`

Later, not full re-init every time:

- On startup, if triage index is missing or stale vs cache, run bootstrap again
- After each successful Gmail sync, refresh triage index from the latest cache

## What Is Already Shipped

In this repo the funnel is wired, not only planned:

- `gmail_sync_service -> gmail_cache -> EmailTriageService.refresh_index()`
- Triage bootstrap / catch-up on startup
- Triage index refresh after each successful Gmail sync
- Dashboard `priorityInbox` consumes triage
- Daily summary reads unified triage instead of re-scoring everywhere

Intent:

- Inbox cache = raw message snapshot
- Triage index = unified triage
- Dashboard / summary / reminder read these only—no duplicate priority rules per surface

## Light Metrics and Funnel Quantification

A light metrics layer answers “is the funnel doing something,” not only UI feel.

`GET /email-triage/metrics` returns:

- `itemCount`
- `metrics.runCount`
- `metrics.successCount`
- `metrics.failureCount`
- `metrics.lastStatus`
- `metrics.lastDurationMs`
- `metrics.lastInputCount`
- `metrics.lastTriagedCount`
- `metrics.lastUrgentCount`
- `metrics.lastActionableCount`
- `metrics.lastLowValueCount`
- `metrics.lastUrgentRate`
- `metrics.lastActionableRate`
- `metrics.lastLowValueRate`
- `recentRuns`

Backend logs also emit funnel events:

- `email_triage.ensure_current.refresh_needed`
- `email_triage.refresh.begin`
- `email_triage.refresh.progress`
- `email_triage.refresh.ready`
- `email_triage.refresh.failed`
- `gmail_sync.triage_refresh.begin`
- `gmail_sync.triage_refresh.ready`

These metrics answer:

- Whether triage actually ran
- Input message count
- How many urgent / actionable / low-value
- Whether the last refresh succeeded

What they do not fully cover yet is user action loops, e.g.:

- How often priority inbox is opened
- Whether actionable mail was actually replied to
- False positives among urgent hits

That is the next layer of behavioral instrumentation—not in this light metrics round.

## What the Project Already Has

The repo has the front half of the funnel, but logic is scattered:

- Noise / bulk / newsletter filtering:
  - `shared/inbox_cache.py`
- Rule-based urgent detection:
  - `agents/email-agent/tools/urgent.py`
- Dashboard priority inbox scoring:
  - `backend/app/services/common/dashboard_status.py`
- Daily summary important / reply-needed scoring:
  - `backend/app/services/daily_summary_service.py`
- Contact priority and relationships:
  - `backend/app/services/triage/contact_repository.py`
- Inbox operational cache:
  - `backend/app/services/gmail/gmail_cache.py`

So:

- `Layer 0` partially exists
- `Layer 1` partially exists
- Action surfaces exist: dashboard / briefing / reminder / follow-up digest

The problem:

**Multiple scattered rules; no single arbitration layer.**

## Biggest Structural Issue Today

The same email can get different scores in:

- Chat tool `show_urgent_emails()`
- Dashboard `priorityInbox`
- Daily summary `important_score`

So step one is not “add models,” but:

**Unify on one central triage service.**

## Recommended Service Boundary

Add:

- `backend/app/services/triage/email_triage_service.py`

It becomes the only mail triage entry point.

These modules should consume its output:

- `dashboard_status.py`
- `daily_summary_service.py`
- `scheduled_task_service.py`
- `urgent.py`
- Later: reminders, summaries, notification delivery

## Unified Funnel Design

### Layer 0: Noise filter

Goals:

- Filter obvious low-value mail first
- Provide initial category hints

Prefer existing signals:

- Gmail category labels
- `List-Unsubscribe`
- `List-Id`
- `Precedence`
- sender `no-reply`
- subject / snippet bulk-like patterns

Outputs:

- `is_noise`
- `noise_type`
- `noise_score`
- `category_candidate`

### Layer 1: Category classifier

Goals:

- Answer “what category is this message”

First version: rules and patterns, not ML.

Cover at least:

- `meeting`
  - meeting / calendar / schedule / call / zoom / interview
- `finance`
  - invoice / payment / receipt / billing / expense
- `security`
  - security / verify / password / sign in
- `reply_needed`
  - please confirm / awaiting your reply / gentle reminder / follow up
- `newsletter`
  - promotions / list-unsubscribe / marketing
- `notification`
  - service update / automated notice / system event
- `project_update`
  - project / feature / launch / spec / review

Outputs:

- `category`
- `category_confidence`
- `category_reasons`

### Layer 2: Priority signal extractor

Goals:

- Extract priority signals, not final priority in one shot

First version extracts:

- `deadline_detected`
- `deadline_text`
- `deadline_ts`
- `deadline_hours_left`
- `action_required`
- `action_type`
- `reply_pressure`
- `sender_importance_score`
- `thread_pressure`
- `negative_urgency_detected`

Data sources stable in the project today:

- `subject`
- `from`
- `snippet`
- `labelIds`
- `internalDate`
- contact `priority`
- contact `relationship`

Not yet depending on:

- Fully cleaned body
- Quoted ratio
- Attachment parsing
- Historical open / reply behavior

### Layer 3: Strong rule engine

Goals:

- Quickly catch clearly high-risk / high-urgency mail

Consolidate scattered rules, at least:

- `urgent / asap / deadline / action required`
- `today / tonight / tomorrow / EOD / by 5pm`
- `please confirm / awaiting your reply / gentle reminder`
- `security / verify / approval / confirm`
- High-priority contact weighting
- Bulk-like downranking

Negative signals:

- `not urgent`
- `no rush`
- `when convenient`

Outputs:

- `rule_score`
- `matched_rules`
- `priority_candidate`

### Layer 4: Decision aggregator

Goals:

- Single arbitration, one final result

First version: no lightweight model, no LLM reviewer.

Suggested logic:

- Very high `noise_score` and no high-risk signal → `P3_LOW_VALUE`
- Meeting class and imminent start → `P0` or `P1`
- Security / payment / approval with time pressure → `P0`
- Clear reply or follow-up pressure → `P1`
- Normal work mail → `P2`
- Bulk / low-value update → `P3`

Outputs:

- `priority_label`
- `priority_score`
- `confidence`
- `reasons`
- `deadline_info`
- `suggested_action`

## Relationship Between Category and Priority

They differ but can be produced in one funnel.

Typical combinations:

- `meeting + P0`
  - Soon, confirmation needed, important contact
- `meeting + P2`
  - Ordinary meeting notice, no immediate action
- `finance + P0`
  - Payment due today, overdue, approval needed now
- `newsletter + P3`
  - Low value, cleanup candidate
- `reply_needed + P1`
  - Needs handling, not necessarily instant fire

## Wiring Into the Project

### 1. Dashboard

`priorityInbox` should read unified triage, not compute `_priority_score()` locally.

### 2. Daily summary

`important_score` and `reply_needed` should use:

- `category`
- `priority_label`
- `reasons`

### 3. Urgent tool

`show_urgent_emails()` becomes a viewer over unified triage, not separate scoring.

### 4. Scheduled tasks

Later:

- `daily_briefing`
- `follow_up_digest`
- `meeting_brief`

Can filter and sort directly from triage.

## First-Version Data Layout

The project should not jump to PostgreSQL + Kafka + feature store yet.

Stay on local files; add:

- `data/email_triage_index.json`
  - Recent triage results
- `data/email_triage_feedback.json`
  - User corrections and behavioral feedback
- Optional:
  - `data/email_triage_rules.json`
  - Gradually externalize rules from code

Consistent with existing:

- `memory/*.json`
- `scheduled_tasks.json`
- `gmail_sync_state.json`

Minimal change surface.

## First-Version Implementation Order

### Step 1

Add `EmailTriageService`.

### Step 2

Move scattered rules into it:

- `shared/inbox_cache.py`
- `urgent.py`
- `dashboard_status.py`
- `daily_summary_service.py`

### Step 3

Unified outputs:

- `category`
- `priority_label`
- `priority_score`
- `confidence`
- `reasons`
- `suggested_action`

### Step 4

Wire results to:

- Dashboard
- Daily briefing
- Follow-up digest
- Secretary reminders

## Phase Two

After v1 stabilizes:

### 1. Feature builder

Prioritize:

- `body_clean`
- `deadline_ts`
- `deadline_hours_left`
- `action_type`
- `followup_count`
- `sender_importance_score`
- `thread_pressure`

### 2. Feedback loop

Collect:

- Quick open vs ignore
- Quick reply vs not
- Manual label edits
- Manual archive or ignore

### 3. Personalization weighting

Rule weighting first, not per-user micro-models:

- Boss / customer / high-priority contact boost
- Long-ignored sources downrank
- Senders often needing fast replies boost

## Phase Three: Models

### 1. Lightweight models

After enough feedback:

- Logistic regression
- XGBoost

### 2. Gray-zone LLM reviewer

Last, and only for gray zones:

- Rule vs model conflict
- Important contact but ambiguous semantics
- Complex deadline phrasing
- Polite but dependency-heavy task mail

No full-mail LLM review for everything.

## Not Recommended Immediately

Not a fit for immediate rollout:

- Kafka
- PostgreSQL as primary mail store
- Full embedding pipeline
- Full-mail LLM review
- Complex per-user micro-models

## Conclusion

For this project, the right first step is not “ship a full production funnel,” but:

**Build a unified `EmailTriageService` that outputs `category + priority` in one funnel; ship Layer 0 + Layer 1 + Layer 2 + Aggregator first.**

After that stabilizes, add:

- Feature builder
- Feedback loop
- Personalization
- Lightweight model
- Gray-zone LLM reviewer
