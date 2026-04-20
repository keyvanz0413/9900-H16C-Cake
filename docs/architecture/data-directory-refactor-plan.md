# `data/` Directory Refactor Plan

This document addresses one problem:

**Under the current `data/` layout, cache, memory, runtime state, and artifacts are mixed together, and names are not always intuitive—maintenance will get harder.**

The goal is not a large system rewrite, but clarifying data boundaries first.

## Current Issues

In today’s code, `data/` mixes at least four kinds of content:

- Cache
  - `inbox_cache.json`
  - `email_triage_index.json`
- Runtime state
  - `gmail_sync_state.json`
  - `email_agent_sessions.json`
  - `scheduled_tasks.json`
  - `scheduled_task_runs.json`
  - `*.lock`
- Long-term preferences / memory
  - `memory/preferences.json`
  - `memory/memory_profile.json`
  - `memory/memory_journal.json`
  - `writing_style.md`
  - `contacts.csv`
- Artifacts
  - `daily_summary.md`
  - `daily_summaries/`
  - `briefings/`
  - `memory_curations/`

The clearest structural problems:

1. The `data/` root mixes different lifecycle data.
2. Filenames under `memory/` lean technical, not product semantics.
3. Backend `memory/*.json` coexists with runtime `memory.md` semantics.
4. Some files are really “cache” or “state” but sit next to long-term memory.
5. Some names are opaque, e.g. `memory_profile.json`, `memory_journal.json`, `summaries.json`.

## What External Designs Are Worth Borrowing

### OpenClaw

Worth taking:

- Separate human-editable memory from runtime state
- Treat workspace as source of truth
- Do not mix derived indexes and ephemeral state with long-term memory

Do not copy wholesale:

- Making the entire workspace memory is too heavy for the current mailbox product

### Claude Code

Worth taking:

- Stable rules, automatic memory, and config split by mechanism
- Long-term context still split into layers
- Project-level vs machine-local data separated

Do not copy wholesale:

- Its machine-local layout fits a local coding agent more than this repo’s self-hosted structure

### Cline

Worth taking:

- Filenames describe business meaning, not implementation detail
- At a glance you know what a file is for

### Letta

Worth taking:

- Core memory vs archived memory separated
- Small, stable core memory in context
- Large history loaded on demand

## Refactor Principles

Four principles only:

1. Rebuildable data in one layer.
2. Frequently changing runtime state in one layer.
3. Stable preferences and user profile in one layer.
4. Human-facing artifacts in one layer.

Plus one naming rule:

**Prefer product semantics over implementation names.**

## Target Directory Layout

Converge `data/` into four layers:

```text
data/
  cache/
    inbox_cache.json
    email_triage_index.json

  state/
    gmail_sync_state.json
    email_agent_sessions.json
    scheduled_tasks.json
    scheduled_task_runs.json
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
    session_snapshot.json
    unsubscribe_preferences.json
    projects.json

  outputs/
    daily_summary.md
    daily_summaries/
    briefings/
    memory_curations/
```

## Responsibility per Layer

### `cache/`

Responsibilities:

- Rebuildable data
- Usually from provider sync or derived indexes

Characteristics:

- Safe to lose and rebuild
- Should not hold long-term preferences

Good fits today:

- `inbox_cache.json`
- `email_triage_index.json`

### `state/`

Responsibilities:

- Current running system state
- Includes sync, session, queues, scheduling, locks

Characteristics:

- High update frequency
- Not user long-term preferences
- Not ideal as agent long-term memory

Good fits today:

- `gmail_sync_state.json`
- `email_agent_sessions.json`
- `scheduled_tasks.json`
- `scheduled_task_runs.json`
- `*.lock`

### `profile/`

Responsibilities:

- Stable user preferences, contact relationships, writing style, memory events

Characteristics:

- Long-term layer for “who the user is, how they work, how they decide”
- Best source of long context for the agent

Good fits today:

- `contacts.csv`
- `writing_style.md`
- `writing_style_feedback.json`
- `preferences.json`
- `memory_profile.json` after rename, placed here
- `memory_journal.json` after rename, placed here
- `short_term.json` after rename, here or under `state/`
- `unsubscribe_preferences.json`
- `projects.json`

### `outputs/`

Responsibilities:

- System-generated human-readable files
- Results, not source of truth

Characteristics:

- Can be regenerated
- Mainly for reading and review

Good fits today:

- `daily_summary.md`
- `daily_summaries/`
- `briefings/`
- `memory_curations/`

## Naming Recommendations

This is where the biggest wins are.

### Keep as-is

- `inbox_cache.json`
- `email_triage_index.json`
- `gmail_sync_state.json`
- `email_agent_sessions.json`
- `writing_style.md`

These are already understandable.

### Rename

- `memory_profile.json` → `user_profile.json`
  - It holds curated long-term profile, not just “memory”
- `memory_journal.json` → `events.json`
  - It is effectively an event stream
- `short_term.json` → `session_snapshot.json`
  - Closer to reality: compressed snapshot of the current session
- `summaries.json` → split into
  - `daily_summaries_index.json`
  - `conversation_summaries.json`
  - `weekly_summaries.json`

If splitting is deferred, at least rename to:

- `summary_index.json`

### Reinterpret

- `contacts.csv`
  - Not only “contacts”; it already behaves like a sender registry
  - If newsletter senders and real contacts stay mixed, consider splitting into:
    - `contacts.csv`
    - `senders.csv`

## Conflicts to Resolve First

### 1. `memory.md` vs `memory/*.json`

Runtime still has:

- `data/memory.md`

While backend primary memory is:

- `data/memory/*.json`

Recommendation:

- Stop expanding `memory.md`’s role
- Demote it explicitly to legacy compatibility
- Eventually use `user_profile.json + preferences.json + writing_style.md` as the real long-term memory entry points

### 2. `short_term.json` vs `email_agent_sessions.json`

Both feel like session state but differ:

- `email_agent_sessions.json`
  - Real chat history, draft session, action session
- `short_term.json`
  - Compressed current-session summary

Recommendation:

- Classify the former clearly as `state/`
- If the latter remains, rename to `session_snapshot.json`

### 3. `summaries.json` vs `outputs/`

Today:

- `summaries.json` holds daily / weekly / conversation summaries
- `daily_summary.md`
- `daily_summaries/`
- `briefings/`

All are “some kind of summary.”

Recommendation:

- `profile/` keeps structured summary index only
- `outputs/` keeps markdown artifacts only

## Minimal Migration Plan

Do not move everything at once. Four steps.

### Step 1: Add a unified path layer

Add clearer path definitions first, e.g.:

- `cache_dir`
- `state_dir`
- `profile_dir`
- `outputs_dir`

No physical moves yet—abstraction only.

### Step 2: Backward compatibility for new paths

Allow:

- Prefer new paths
- Fallback to old paths

So migration can be phased without breaking the system.

### Step 3: Move clearest files first

Priority moves:

- `inbox_cache.json` → `cache/`
- `email_triage_index.json` → `cache/`
- `gmail_sync_state.json` → `state/`
- `email_agent_sessions.json` → `state/`
- `scheduled_tasks.json` → `state/`
- `scheduled_task_runs.json` → `state/`

These boundaries are the clearest.

### Step 4: Move `memory/` last

`memory/` has the most ripple effects—do it last.

Suggested order:

1. `memory_profile.json` → `profile/user_profile.json`
2. `memory_journal.json` → `profile/events.json`
3. `short_term.json` → `profile/session_snapshot.json` or `state/session_snapshot.json`
4. `summaries.json` → split or rename

## If Evolution Continues

### Keep in `profile/`

- Writing style
- User profile
- Stable preferences
- Contact importance
- Unsubscribe preferences
- Long-term project focus

### Put in `outputs/`

- Candidate briefs
- Customer issue briefs
- Daily summary
- Meeting brief
- Follow-up digest

### Put in `cache/`

- Any rebuildable provider-derived index
- Workflow planner–generated email brief cache

## External Ideas Worth Summarizing

In one line:

**Borrow OpenClaw’s separation of memory and state, Claude Code’s mechanism-based long-term context storage, Cline’s filenames that state purpose, and Letta’s split between core and archived memory.**

## End State

After refactor, aim for:

- Opening `data/` makes each file type obvious
- New features land in the right layer
- The agent no longer stitches long-term context from a mixed pile
- User habit learning, workflow briefs, and proactive services do not further scatter the tree
