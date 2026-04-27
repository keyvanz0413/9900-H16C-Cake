# Unified Data Layout and Personalized Workflow Refactor Plan

This document merges the following two plans into one executable path:

- `docs/architecture/data-directory-refactor-plan.md`
- `docs/workflow/personalized-email-workflow-plan.md`

The goal is not to run two large projects in parallel, but to converge them into a sequenced, incrementally shippable, reversible refactor plan.

---

## 1. Bottom Line First

Proceed in this order:

1. Lay the foundation: data paths and directory layering.
2. Add compatible migration so old and new paths can coexist.
3. Converge long-term memory into one unified `user_profile` semantic layer.
4. Finally wire personalized workflows to triage and agent skills.

Why:

- Long-term memory already treats `data/memory/*.json` as the primary source of truth.
- Turning on personalized workflow now by adding `data/user_profile.json`, `data/email_briefs.json`, and `data/learned_patterns.json` without layout work would further scatter the `data/` root and create a second long-term profile source.
- Backend and agent runtime path definitions still lack directory layering; new features would only deepen path coupling.

Core principle for this refactor:

**Unify data boundaries first, then add intelligent workflows.**

---

## 2. Real Constraints in the Code Today

Not every doc assumption holds in code. There are six practical constraints:

### 2.1 Path layer is still thin

The backend currently exposes only:

- `data_dir`
- `memory_dir`

The agent runtime exposes only a few root-level file paths:

- `contacts.csv`
- `writing_style.md`
- `writing_style_feedback.json`
- `urgent_emails.md`
- `meetings.json`

There is still no:

- `cache_dir`
- `state_dir`
- `profile_dir`
- `outputs_dir`

### 2.2 Long-term memory already has a source of truth

`MemoryStore` already treats these as primary storage:

- `data/memory/preferences.json`
- `data/memory/tasks.json`
- `data/memory/projects.json`
- `data/memory/summaries.json`
- `data/memory/memory_journal.json`
- `data/memory/memory_profile.json`
- `data/memory/unsubscribe_preferences.json`
- `data/memory/short_term.json`

So `user_profile` in the personalized workflow cannot introduce a separate storage model—it must evolve from here.

### 2.3 Runtime still uses `memory.md` directly

The agent runtime still initializes:

- `data/memory.md`

That is a different semantic world from backend `memory/*.json`. Do not expand this file’s role; later it can only be a compatibility layer.

### 2.4 Routing and skill selection still “look at this user utterance”

Today:

- `AgentRequestRouter` only looks at the user message text
- `AgentSkillSelector` is mostly keyword- and bundle-based

Not yet used:

- Triage results
- User profile
- Thread-level workflow hints

So personalized workflow should not be crammed into the existing router; add a separate planner layer.

### 2.5 Triage refresh already has a natural hook

After Gmail sync completes, the system already refreshes:

- `email_triage_index.json`

So the most natural place for future brief precomputation is not the chat entrypoint, but:

- After Gmail sync
- After triage refresh

### 2.6 The first briefing workflow should not be candidate

Existing tools are relatively strong at:

- Searching mail
- Reading thread context
- Running triage
- Reading contacts

They are relatively weak at:

- Reading attachments
- Parsing PDF résumés
- Extracting portfolio content

So the first personalized closed loop should not be `candidate-briefing`; it should be thread-context-only:

- `customer-briefing`

---

## 3. Goals of This Refactor

When done, five outcomes:

1. `data/` is layered by lifecycle; new files have an obvious home.
2. One source of truth for long-term profile—no parallel `memory_profile` semantics vs a separate `user_profile` system.
3. `memory.md` is demoted to compatibility output, not long-term memory truth.
4. After triage, produce `workflow_tag` and precompute structured briefs for high-value mail.
5. User behavior is logged first, then learned into stable long-term preferences—not one request rewriting the profile.

---

## 4. Non-Goals

Not in scope this round:

- Vector database migration
- Multi-agent orchestration
- Generic memory platform refactor
- Attachment parsing / RAG first
- Deleting all legacy paths in one shot
- Shipping multiple briefing workflows at once

---

## 5. Target Directory Layout

Converge toward:

```text
data/
  cache/
    inbox_cache.json
    email_triage_index.json
    email_briefs.json

  state/
    gmail_sync_state.json
    email_agent_sessions.json
    scheduled_tasks.json
    scheduled_task_runs.json
    session_snapshot.json
    tasks.json
    meetings.json
    locks/
      gmail_sync_loop.lock
      scheduled_task_loop.lock

  profile/
    contacts.csv
    writing_style.md
    writing_style_feedback.json
    preferences.json
    user_profile.json
    events.json
    projects.json
    unsubscribe_preferences.json
    summary_index.json
    learned_patterns.json

  outputs/
    daily_summary.md
    daily_summaries/
    briefings/
    memory_curations/
    urgent_emails.md

  memory.md
```

Notes:

- Keep `memory.md` at the root for now, as legacy compatibility only.
- `email_briefs.json` is structured cache—belongs under `cache/`.
- `learned_patterns.json` is stable learned preference output—belongs under `profile/`.
- `urgent_emails.md` is rebuildable, human-readable output—better under `outputs/`.
- `session_snapshot.json` matches semantics better than `short_term.json`, and it belongs under `state/`, not long-term profile.

---

## 6. Legacy File to New Path Mapping

| Current file | Target file | Type | Notes |
| --- | --- | --- | --- |
| `data/inbox_cache.json` | `data/cache/inbox_cache.json` | cache | Rebuildable |
| `data/email_triage_index.json` | `data/cache/email_triage_index.json` | cache | Rebuildable derived index |
| `data/gmail_sync_state.json` | `data/state/gmail_sync_state.json` | state | Runtime state |
| `data/email_agent_sessions.json` | `data/state/email_agent_sessions.json` | state | Chat/draft/action session |
| `data/scheduled_tasks.json` | `data/state/scheduled_tasks.json` | state | Schedule definitions |
| `data/scheduled_task_runs.json` | `data/state/scheduled_task_runs.json` | state | Run history |
| `data/gmail_sync_loop.lock` | `data/state/locks/gmail_sync_loop.lock` | state | Lock file |
| `data/scheduled_task_loop.lock` | `data/state/locks/scheduled_task_loop.lock` | state | Lock file |
| `data/meetings.json` | `data/state/meetings.json` | state | Meetings are runtime state |
| `data/memory/short_term.json` | `data/state/session_snapshot.json` | state | Compressed session state |
| `data/memory/tasks.json` | `data/state/tasks.json` | state | Current task queue |
| `data/contacts.csv` | `data/profile/contacts.csv` | profile | Stable contact semantics |
| `data/writing_style.md` | `data/profile/writing_style.md` | profile | Long-term style |
| `data/writing_style_feedback.json` | `data/profile/writing_style_feedback.json` | profile | Long-term style feedback |
| `data/memory/preferences.json` | `data/profile/preferences.json` | profile | Stable preferences |
| `data/memory/memory_profile.json` | `data/profile/user_profile.json` | profile | Same source of truth, clearer name |
| `data/memory/memory_journal.json` | `data/profile/events.json` | profile | Event stream |
| `data/memory/projects.json` | `data/profile/projects.json` | profile | Long-term project focus |
| `data/memory/unsubscribe_preferences.json` | `data/profile/unsubscribe_preferences.json` | profile | Long-term unsubscribe prefs |
| `data/memory/summaries.json` | `data/profile/summary_index.json` | profile | Phase 1: rename only, no split yet |
| `data/daily_summary.md` | `data/outputs/daily_summary.md` | outputs | Human-facing artifact |
| `data/daily_summaries/` | `data/outputs/daily_summaries/` | outputs | Historical artifacts |
| `data/briefings/` | `data/outputs/briefings/` | outputs | Human-readable briefing output |
| `data/memory_curations/` | `data/outputs/memory_curations/` | outputs | Human-readable curation output |
| `data/urgent_emails.md` | `data/outputs/urgent_emails.md` | outputs | Rebuildable markdown output |
| `data/memory.md` | `data/memory.md` | legacy | Kept for compatibility, not source of truth |

New files:

| New file | Target file | Type | Notes |
| --- | --- | --- | --- |
| `email_briefs.json` | `data/cache/email_briefs.json` | cache | Workflow structured brief cache |
| `learned_patterns.json` | `data/profile/learned_patterns.json` | profile | Stable behavioral patterns |

---

## 7. Key Design Decisions

### 7.1 Introduce the unified path layer before moving files

Do not hand-edit paths in each service. Define one unified data layout as the single source of truth.

Add a shared path module, e.g.:

- `shared/data_layout.py`

It should expose:

- `cache_dir`
- `state_dir`
- `locks_dir`
- `profile_dir`
- `outputs_dir`
- `legacy_memory_dir`
- Canonical file paths
- Legacy vs new path compatibility rules

Backend and agent runtime both read paths from here—no duplicated definitions.

### 7.2 Reads: prefer new path, fallback to legacy

During migration, all stores and services:

- Read new path first
- If missing, fall back to old path

Ship the path layer without moving every file at once.

### 7.3 Writes: canonical path only

After migration starts, new code writes only canonical paths.

One exception:

- `memory.md` may still be regenerated during compatibility

Otherwise avoid long-term dual writes—that recreates multiple sources of truth.

### 7.4 `user_profile` is not a second store

`user_profile.json` is not a brand-new profile system; it is the normalized evolution of `memory_profile.json`.

Phase 1:

- Move filename to `profile/user_profile.json`
- Keep `MemoryStore.get_memory_profile()` but read the new path internally
- Add `get_user_profile()` / `save_user_profile()` as the new semantic API

So:

- **Merge sources of truth**
- **Migrate interfaces gradually**

### 7.5 Do not split `summary_index.json` in phase 1

`summaries.json` may eventually split into daily / weekly / conversation files, but phase 1 should not take that complexity.

Phase 1:

- Clarify file semantics only
- `summaries.json` → `summary_index.json`

Split further after paths stabilize.

### 7.6 `memory.md` is export-only, not primary storage

While runtime still depends on `Memory(memory_file=...)`:

- Keep `memory.md`
- Generate its contents from `user_profile + preferences + session_snapshot + tasks`
- It is no longer the write path for long-term profile

### 7.7 Workflow planner is separate from request router

`AgentRequestRouter` today:

- Picks bundle from the user’s current utterance

`EmailWorkflowPlanner` should:

- From `triage item + user profile + thread context` produce `workflow_tag`
- Decide `recommended_skill`
- Decide `brief_type`

So:

- Router sets tool capability boundaries for this turn
- Planner decides what workflow this email should follow

Do not merge them into one class.

### 7.8 First briefing: read-only, thread-based

First workflow suggestion:

- `customer-briefing`

Not first:

- `candidate-briefing`

Attachment/résumé parsing is not in place yet; candidate assessment would widen scope too much.

---

## 8. Target Architecture

### 8.1 Data layer

Add a unified data layout layer; all services depend on canonical paths, not ad hoc `data/...` strings.

### 8.2 Memory layer

Keep `MemoryStore` as the main entry for long-term profile and preferences, but move internal paths under `profile/` and `state/`.

Later, split `MemoryStore` into:

- `ProfileStore`
- `SessionStateStore`

Not required in phase 1.

### 8.3 Workflow layer

Add:

- `backend/app/services/workflow/email_workflow_planner.py`

Inputs:

- Triage item
- User profile
- Optional thread context summary

Outputs:

- `workflow_tag`
- `recommended_skill`
- `brief_type`
- `priority_for_precompute`

### 8.4 Brief cache layer

Add:

- `backend/app/services/workflow/email_brief_store.py`

Cache file:

- `data/cache/email_briefs.json`

Suggested key fields at minimum:

- `message_id`
- `thread_id`
- `workflow_tag`
- `brief_type`
- `triage_fingerprint`
- `profile_fingerprint`
- `generated_at`

So cache invalidates naturally when triage or profile changes.

### 8.5 Learning layer

Add:

- `backend/app/services/memory/learned_pattern_store.py`

Storage:

- `data/profile/learned_patterns.json`

Phase 1 only:

- Record stable behavioral signals
- Emit suggestions after thresholds

Phase 1 not:

- Change long-term profile from a single click

### 8.6 Precompute vs lazy generation

Brief generation has two paths:

- Precompute: after Gmail sync + triage refresh
- Lazy: when the user opens a thread or asks about a message—generate on cache miss

So:

- Normal access stays fast
- Failures do not block core functionality

---

## 9. Phased Execution

The order below is the recommended execution order.

## Phase 0: Inventory and guardrails

Goals:

- Define migration boundaries and regression tests before changes explode.

Deliverables:

- Inventory of current `data/` files
- List of code that hardcodes `data/...` paths
- Path and compatibility migration test checklist

Steps:

1. List all `data/` files and classifications.
2. List all backend/agent code points that concatenate `data/...`.
3. Add path resolution tests that lock old behavior.
4. Clarify which services may depend on legacy paths; new code uses new paths only.

Done when:

- Files and call sites involved in migration are listed.
- At least one path-layer test suite guarantees “path change, same semantics.”

## Phase 1: Unified path layer

Goals:

- Introduce canonical path abstraction without moving real files yet.

Deliverables:

- Shared data layout module
- Unified path access for backend and agent

Steps:

1. Add shared path module, e.g. `shared/data_layout.py`.
2. Define `cache_dir` / `state_dir` / `profile_dir` / `outputs_dir` / `locks_dir`.
3. Map canonical file paths to legacy paths.
4. Extend `backend/app/services/common/project_paths.py` from this layer.
5. Extend `agents/email-agent/runtime/project_paths.py` the same way.
6. Add path unit tests for backend and runtime.

Done when:

- New code does not hand-build `data/foo.json`.
- Backend and runtime resolve the same canonical path for the same file.

## Phase 2: Migrate cache/state files

Goals:

- Move the clearest cache/state files first.

Deliverables:

- All cache/state services support canonical path + legacy fallback

Steps:

1. Move `GmailCache` to `cache/inbox_cache.json`.
2. Move `EmailTriageStore` to `cache/email_triage_index.json`.
3. Move `GmailSyncStore` to `state/gmail_sync_state.json`.
4. Move `EmailAgentSessionStore` to `state/email_agent_sessions.json`.
5. Move `ScheduledTaskStore` to `state/scheduled_tasks.json` and `state/scheduled_task_runs.json`.
6. Move loop locks to `state/locks/`.
7. Move `CalendarService` and meeting tools to `state/meetings.json`.
8. Add legacy path compatibility tests.

Done when:

- Cache/state files work from new paths.
- Missing old paths do not crash.
- Daily sync / triage / scheduled tasks do not regress.

## Phase 3: Migrate memory data under profile/state

Goals:

- Split long-term profile, preferences, and session snapshot from `data/memory/` into the right layers.

Deliverables:

- `MemoryStore` uses new paths
- `user_profile` is the canonical filename

Steps:

1. Move `preferences.json` to `profile/preferences.json`.
2. Move `memory_profile.json` to `profile/user_profile.json`.
3. Move `memory_journal.json` to `profile/events.json`.
4. Move `projects.json` to `profile/projects.json`.
5. Move `unsubscribe_preferences.json` to `profile/unsubscribe_preferences.json`.
6. Move `summaries.json` to `profile/summary_index.json`.
7. Move `short_term.json` to `state/session_snapshot.json`.
8. Move `tasks.json` to `state/tasks.json`.
9. Add new semantic APIs on `MemoryStore`:
   - `get_user_profile()`
   - `save_user_profile()`
   - `get_session_snapshot()`
10. Keep legacy APIs as compatibility shims:
   - `get_memory_profile()`
   - `get_short_term()`

Done when:

- Long-term profile has one canonical name: `user_profile.json`.
- `short_term` clearly lives under `state/`.
- Existing `MemoryStore` callers do not need large simultaneous edits.

## Phase 4: Outputs and legacy export cleanup

Goals:

- Separate human-readable artifacts from structured sources of truth.

Deliverables:

- `outputs/` in use
- `memory.md` demoted to compatibility export

Steps:

1. Move `daily_summary.md` to `outputs/`.
2. Move `daily_summaries/` to `outputs/`.
3. Move `briefings/` to `outputs/`.
4. Move `memory_curations/` to `outputs/`.
5. Move `urgent_emails.md` to `outputs/`.
6. Add a `memory.md` exporter that generates legacy markdown from profile/state.
7. Keep runtime `Memory(memory_file=...)` reading exported `data/memory.md`.

Done when:

- Human-readable output and structured sources of truth are not mixed.
- Runtime no longer treats `memory.md` as the real source of truth.

## Phase 5: Add workflow planner

Goals:

- Insert planning between triage and skills: “what this email means for this user.”

Deliverables:

- `email_workflow_planner.py`
- Planner unit tests

Steps:

1. Add pure-logic `EmailWorkflowPlanner` service.
2. Inputs initially limited to:
   - Triage item
   - User profile
   - Optional thread metadata
3. Outputs:
   - `workflow_tag`
   - `recommended_skill`
   - `brief_type`
   - `precompute_priority`
4. First version supports only a few workflows:
   - `needs_customer_brief`
   - `needs_meeting_brief`
   - `needs_human_review`
5. Do not change `AgentRequestRouter`.
6. Do not force-change `AgentSkillSelector` defaults; add a planner-aware extension hook only.

Done when:

- Planner is testable and reusable in isolation.
- Stable workflow decisions before wiring the agent.

## Phase 6: Brief cache and first workflow

Goals:

- Ship the first end-to-end personalized workflow.

Deliverables:

- `email_briefs.json`
- `customer-briefing` workflow

Steps:

1. Add `EmailBriefStore` at `cache/email_briefs.json`.
2. Define `customer_brief` shape:
   - customer
   - latest_state
   - requested_action
   - deadline_or_risk
   - suggested_response_direction
3. With existing tools, thread-only briefs first—no attachment briefs.
4. Add `customer-briefing` skill under `thread_deep_read`.
5. Lazy generation first:
   - User opens thread
   - Generate on cache miss
6. Keep structured cache; optionally emit markdown under `outputs/briefings/`.

Done when:

- At least one workflow runs triage → planner → brief cache → agent skill.
- No new attachment parsing required.

## Phase 7: Wire brief precompute into backend flow

Goals:

- Precompute in the background, not only when the user opens a thread.

Deliverables:

- Brief precompute after Gmail sync

Steps:

1. After triage refresh in `GmailSyncService`, invoke planner.
2. Precompute only for high-value mail:
   - `P0_URGENT`
   - `P1_ACTION_NEEDED`
   - High-confidence workflow tags
3. Cap precompute volume per sync to avoid runaway sync time.
4. On failure, log only—do not block sync.
5. Add cache staleness checks to avoid redundant generation.

Done when:

- Most important mail after sync has brief cache.
- Sync duration does not grow unbounded from brief precompute.

## Phase 8: Learning layer records only—no auto rewrite

Goals:

- Foundation for personalization without unpredictable system behavior.

Deliverables:

- `learned_patterns.json`
- Behavioral logging and threshold aggregation

Steps:

1. Define behavioral events to log:
   - User often asks for shorter output
   - User often asks for next step first
   - User often expands risk sections
2. Add `LearnedPatternStore`.
3. Accumulate counts and threshold checks only.
4. After thresholds, write `learned_patterns.json`.
5. Merge into `user_profile` only after explicit confirmation or stable thresholds.

Done when:

- Single actions do not drift long-term profile.

## Phase 9: Remove legacy paths

Goals:

- After new paths stabilize, drop legacy fallbacks.

Deliverables:

- One-shot cleanup script
- Zero remaining legacy dependencies

Steps:

1. Audit for code still reading old paths.
2. Write migration script to move files to canonical paths.
3. Run migration in local and test environments.
4. Remove read fallback to old paths.
5. Only then consider deleting the old `data/memory/` tree.

Done when:

- All services use canonical paths only.
- Old directories are not required at runtime.

---

## 10. Suggested PRs / Small Steps

For collaboration and regression control, split roughly into these 10 steps:

1. Add unified data layout module—path abstraction only; no physical moves.
2. Wire backend and agent runtime to unified paths; add path tests.
3. Migrate cache/state stores to canonical path + legacy fallback.
4. Migrate `MemoryStore` to `profile/` and `state/` while keeping legacy APIs.
5. Migrate outputs and turn `memory.md` into an export compatibility layer.
6. Add `EmailWorkflowPlanner` and pure-logic tests.
7. Add `EmailBriefStore`; ship lazy `customer-briefing` first.
8. Wire planner + brief cache to `thread_deep_read` skills.
9. Add brief precompute after Gmail sync.
10. Add `LearnedPatternStore`—logging and threshold aggregation first.

The first five are foundation; the last five are intelligence.

---

## 11. Acceptance per Step

To avoid “great plan, vague execution,” each step should have minimal acceptance criteria.

### Path layer

- Backend and agent runtime agree on canonical path for the same file
- Tests still pass after path toggles

### Store migration

- Prefer new path when present
- Still works when new path missing and legacy present
- Critical services start without errors

### Workflow planner

- Stable output for fixed triage + profile inputs
- Testable without external side effects

### Brief cache

- No pointless regeneration for the same message
- Cache invalidates when triage/profile changes

### Learned patterns

- Single actions do not change long-term profile
- Stable learned patterns only after thresholds

---

## 12. Risks and Mitigations

### Risk 1: Path migration breaks runtime

Mitigation:

- Path layer first
- Fallback second
- Physical moves last

### Risk 2: Two user profiles

Mitigation:

- `user_profile.json` must evolve from `memory_profile`
- Do not introduce a second profile store

### Risk 3: Brief precompute slows sync

Mitigation:

- Precompute only high-value mail
- Rate limits
- Failures do not block sync

### Risk 4: Planner vs router confusion

Mitigation:

- Router: user intent and bundle
- Planner: email workflow decision

### Risk 5: First workflow too ambitious

Mitigation:

- First workflow: thread-based `customer-briefing`
- Defer attachment-based `candidate-briefing`

---

## 13. Recommended Execution Order

If starting now:

1. Phase 1: Unified path layer
2. Phase 2: Cache/state migration
3. Phase 3: Profile/state memory migration
4. Phase 4: Outputs and `memory.md` compatibility layer
5. Phase 5: Workflow planner
6. Phase 6: `customer-briefing` + brief cache
7. Phase 7: Precompute after Gmail sync
8. Phase 8: Learned patterns
9. Phase 9: Remove legacy fallback

In short:

- **Level the foundation first**
- **Then ship the first personalized workflow**
- **Then clean up legacy debt**

---

## 14. What to Do Next

If “start now,” the top three steps:

1. Add the unified path layer.
2. Migrate cache/state files first.
3. Extend `MemoryStore` for `user_profile.json` and `session_snapshot.json` semantic paths.

After these, personalized workflow integration stays smooth and new files stop landing in the `data/` root ad hoc.
