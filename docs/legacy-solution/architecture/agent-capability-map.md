# Agent capabilities and tool chains

This document describes only **capabilities that are wired up in code and actually run today**.

It answers two questions:

- What the agent can do right now
- The chain behind each capability: `user request -> route / tool bundle -> active skill -> tool -> cache / provider -> output`

## Overall boundaries

The chat agent is not one giant universal toolkit. The backend routes first, then exposes only the bundle relevant to this turn.

There is also a lightweight skill selection layer, but it applies **inside** the bundle:

- `bundle` decides which tools are visible this turn
- `skill` decides which workflow to prefer this turn
- `skill` cannot expose tools outside the bundle

Unified rules in the prompt today:

- `skill` is only for stable, recurring multi-step workflows
- `tool` is only for atomic retrieval, state reads, queued actions, and similar concrete capabilities
- When there is an active skill, follow the skill workflow first, then decide whether tools are needed
- When there is no active skill, follow the bundle workflow directly
- Do not invent a second workflow just to “do a bit more”

Prompt sections are unified into five blocks:

- `SYSTEM ROUTING`
- `SYSTEM TOOL ACCESS`
- `SYSTEM TURN POLICY`
- `SYSTEM RETRIEVAL HINT`
- `SYSTEM LANGUAGE POLICY`

There are only five bundle types today:

- `read_only_inbox`
  Read-only mailbox tasks such as search, summary, urgent checks
- `thread_deep_read`
  Questions that need full thread context
- `draft_reply`
  Drafts, replies, meeting replies
- `mailbox_action`
  Action requests such as archive, mark read, unsubscribe
- `contact_or_crm`
  Contacts, CRM, important-contact maintenance

Routing entry points:

- [agent_request_router.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/agent/agent_request_router.py)
- [tool_bundles.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/tool_bundles.py)

Skills auto-enabled today:

- `weekly-recap`
- `urgent-triage`
- `thread-briefing`
- `reply-drafting`
- `newsletter-cleanup`

Modeled but not auto-enabled yet:

- `meeting-reply`
- `important-contacts`

Reasons:

- `meeting-reply` tools still include local schedule write paths
- `important-contacts` tools still include direct writes to `contacts.csv`
- Until those write boundaries are tightened, these two skills are not allowed to auto-drive the prompt

## Primary data sources today

The agent mainly consumes these local state files:

- `data/inbox_cache.json`
  Post-sync mailbox snapshot. Most read-mailbox capabilities prefer this first.
- `data/gmail_sync_state.json`
  Gmail sync status, progress, errors, cursors.
- `data/contacts.csv`
  Contacts, relationship, priority.
- `data/writing_style.md`
  Writing style profile.
- `data/meetings.json`
  Local meeting schedule.
- `data/urgent_emails.md`
  Latest urgent-list text artifact.
- `data/email_agent_sessions.json`
  Session, draft session, action session, and other runtime state.
- `data/memory/`
  Short/long-term memory and summaries.

Important notes:

- The **chat agent’s read-mailbox paths are mostly inbox-cache-first**
- **Dashboard / backend are starting to use the triage index**
- But **the chat agent is not triage-index-first yet**

So for chat, weekly summary and urgent checks still rely mainly on `inbox_cache.json` and rules, not directly on `email_triage_index.json`

## Feature matrix

| User capability | route / bundle | Core tools | Primary data | fallback | Current boundary |
| --- | --- | --- | --- | --- | --- |
| Recent / latest / simple search | `read_only_inbox` | `read_inbox()` / `search_emails()` / `get_latest_email_snapshot()` | `inbox_cache.json` | adapter -> live provider | cache-first by default |
| Unanswered check | `read_only_inbox` | `get_unanswered_emails()` | `inbox_cache.json` | live provider | cache-first by default |
| Urgent check | `read_only_inbox` / `thread_deep_read` | `show_urgent_emails()` / `build_urgent_email_list()` | `inbox_cache.json` + `contacts.csv` | provider search | rule scoring; does not read triage index directly |
| Weekly email summary | `read_only_inbox` + fast path | `summarize_weekly_emails()` | `inbox_cache.json` | provider search / read inbox | local stats by default; LLM narrative off by default |
| Full thread read | `thread_deep_read` | `get_email_thread_context()` | provider thread API | cache thread / email body | provider-first here |
| Draft / reply draft | `draft_reply` | `search_emails()` / `get_email_thread_context()` / `load_writing_style()` / `learn_writing_style_from_sent_emails()` | `inbox_cache.json` + `writing_style.md` | provider thread / sent mail | draft then review; no direct send |
| Meeting detection & slot suggestion | `draft_reply` | `detect_meeting_request()` / `get_meeting_schedule()` / `recommend_meeting_slots()` | `meetings.json` | no live calendar fallback | driven by local schedule file today |
| Unsubscribe / archive / mark read | `mailbox_action` | `list_unsubscribe_candidates()` + `queue_*_action()` | `inbox_cache.json` | action queue unavailable | queue for confirmation only; no direct execution |
| Contact / CRM | `contact_or_crm` | `mark_contact_as_important()` / `apply_important_contact_rules()` / `load_google_contacts()` / `init_crm_database()` | `contacts.csv` + Google Contacts + memory | prompt if missing | CRM bootstrap is heavy; not a default action |

## Detailed chains

### 1. Recent mail, latest mail, simple search

Chain:

`user question -> AgentRequestRouter -> read_only_inbox -> AgentEmailTools.read_inbox/search_emails -> inbox cache -> email adapter -> provider`

Behavior:

- `read_inbox()` prefers synced cache
- `search_emails()` uses adapter cache search for simple keywords first
- Live provider is used directly only for complex provider syntax

Code:

- [mailbox_tools.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/mailbox_tools.py#L113)
- [mailbox_tools.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/mailbox_tools.py#L129)

### 2. Unanswered mail check

Chain:

`user question -> read_only_inbox -> get_unanswered_emails() -> inbox_cache.reply_needed_messages() -> provider fallback`

Behavior:

- With cache, estimate “needs reply” locally first
- Fall back to provider when cache does not apply

Code:

- [mailbox_tools.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/mailbox_tools.py#L179)

### 3. Urgent mail check

Chain:

`user question -> read_only_inbox -> show_urgent_emails/build_urgent_email_list -> email_adapter.read_recent_corpus + search_recent_keyword -> inbox cache -> urgent rule scoring -> output`

Scoring signals today:

- urgent keywords
- time pressure
- reply pressure
- important contacts in `contacts.csv`
- bulk / newsletter down-weighting

Code:

- [urgent.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/urgent.py#L113)
- [email_adapter.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/email_adapter.py#L497)
- [contacts.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/contacts.py#L362)

Notes:

- Urgent tools are still rule-based
- Chat does not read `email_triage_index.json` directly

### 4. Weekly email summary

Chain:

`user question -> weekly-summary fast path -> summarize_weekly_emails() -> email_adapter.read_recent_messages/read_recent_corpus -> inbox cache -> local stats -> optional LLM narrative -> output`

Behavior:

- Backend detects whether this is a weekly-summary request
- On hit, fast path skips full agent reasoning
- Prefer `inbox_cache.json`
- Default: local stats and rule-based text only
- With `EMAIL_AGENT_WEEKLY_SUMMARY_USE_LLM=true`, `weekly_summary_writer` adds a 4–6 line summary

Code:

- [email_agent_client.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/agent/email_agent_client.py#L1185)
- [email_agent_client_composition.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/agent/email_agent_client_composition.py#L1046)
- [weekly_summary.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/weekly_summary.py#L457)
- [weekly_summary.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/weekly_summary.py#L636)
- [agent_runtime.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/agent_runtime.py#L78)

### 5. Full thread read

Chain:

`user question -> thread_deep_read -> search_emails() -> get_email_thread_context() -> provider thread API -> cache thread fallback -> email body fallback`

Behavior:

- Thread context prefers Gmail / Outlook thread API
- On provider failure, fall back to cache-assembled thread
- Last resort: single message body only

Code:

- [tool_bundles.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/tool_bundles.py#L115)
- [email_adapter.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/email_adapter.py#L606)

### 6. Drafts, replies, send confirmation

Chain:

`user question -> draft_reply -> search context -> generate draft -> reviewer_agent review -> draft_session / action_session -> user confirmation -> only then send or execute action`

Behavior:

- Draft flow is draft → review → confirm
- Not “user says send” and mail goes out immediately
- Style profile participates in drafting on this path

Code:

- [tool_bundles.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/tool_bundles.py#L123)
- [style.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/style.py#L21)
- [agent_runtime.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/agent_runtime.py#L358)
- [email_agent_client.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/backend/app/services/agent/email_agent_client.py#L1310)

### 7. Writing style learning

Chain:

`user question -> draft_reply / explicit request -> learn_writing_style_from_sent_emails() -> sent mail sample -> style_profiler -> writing_style.md`

Behavior:

- Sample recent sent mail
- Write `data/writing_style.md`
- Later drafts reuse via `load_writing_style()`

Code:

- [style.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/style.py#L29)

### 8. Meeting detection, schedule lookup, slot recommendation

Chain:

`user question -> draft_reply -> detect_meeting_request / get_meeting_schedule / recommend_meeting_slots -> meetings.json -> output`

Behavior:

- Driven by local `meetings.json` today
- No live Google Calendar query dependency

Code:

- [meeting_schedule.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/meeting_schedule.py#L149)
- [meeting_schedule.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/meeting_schedule.py#L163)
- [meeting_schedule.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/meeting_schedule.py#L179)

### 9. Unsubscribe, archive, mark read

Chain:

`user question -> mailbox_action -> list_unsubscribe_candidates()/search -> queue_*_action() -> action session -> user confirmation -> execute`

Behavior:

- Unsubscribe candidates aggregate senders/lists from cache first
- Agent only queues high-risk actions for confirmation
- Does not claim “already unsubscribed / archived” in the same turn

Code:

- [mailbox_tools.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/mailbox_tools.py#L320)
- [mailbox_tools.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/mailbox_tools.py#L413)

### 10. Contact maintenance and CRM

Chain:

`user question -> contact_or_crm -> mark_contact_as_important()/apply_important_contact_rules()/load_google_contacts()/init_crm_database() -> contacts.csv / Google Contacts / memory`

Behavior:

- `mark_contact_as_important()` updates `contacts.csv`
- `apply_important_contact_rules()` bumps boss/client/manager relationships to higher priority
- `load_google_contacts()` imports from Google People API
- `init_crm_database()` is heavier CRM bootstrap; writes into memory

Code:

- [contacts.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/contacts.py#L169)
- [contacts.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/tools/contacts.py#L204)
- [agent_runtime.py](/Users/keyvanzhuo/Documents/CodeProjects/capstone-project-26t1-9900-h16c-cake/agents/email-agent/runtime/agent_runtime.py#L166)

## Three facts that matter most

- Chat agent is mostly **`inbox cache-first`**
- Deep thread read is **`provider-first`**
- Action capabilities are **`queue-for-confirmation-first`**

For future work, the biggest lever is usually not “add more tools” but:

- Have chat consume `email_triage_index.json` more directly
- Align thread / summary / urgent judgment across surfaces
- Keep action confirmation boundaries; do not turn the agent back into a high-risk direct executor
