# Pipeline explicitness and observability checklist

This document is grounded in real flows already in the repository. The goal is not to redesign architecture, but to make the pipeline more explicit, more observable, and with fewer side paths on top of what exists.

## What we mean

### “More explicit”

Make the path easier to see and explain:

`mail arrives -> which category -> why that category -> recommended action -> which workflow matched -> which brief was produced -> what the user finally saw`

Most of these steps already exist, but many decisions live mainly in code and are hard to surface from the UI, logs, and status APIs.

### “Fewer side paths”

A side path is a shortcut that bypasses the main chain.

The ideal main path is:

`sync -> triage -> planner -> workflow -> skill -> reply/action`

If an entry point re-derives classification, skill, or actions on its own, you get a second implicit chain. Some side paths are already closed (e.g. `draft_reply` now prefers workflow context), but fallbacks and main-path boundaries still need to be spelled out.

### “Weak visual workflow management”

Workflows are not missing—they mostly live in code, not in the product.

Developers know about:

- `needs_customer_brief`
- `needs_meeting_brief`
- `needs_hiring_brief`
- `customer-briefing`
- `meeting-briefing`
- `hiring-briefing`

Users and ops still lack a clear workflow map per message: which workflow matched, why, and whether a fallback ran.

### “Observability is not strong enough”

The system runs, but it is still hard to answer:

- How many messages synced today
- How many triaged
- Counts per `category`
- Counts per `suggested_action`
- Which workflows hit most often
- How many briefs generated
- Which messages matched no specialized workflow
- Which replies used main-path skill vs fallback skill
- Which step fails or is slow most often

Logs and a dashboard do not equal full observability. Real observability needs “what happened, why, and how well it worked.”

## Current main path

Given today’s code, the mail pipeline is roughly:

`gmail_sync_service -> gmail_cache -> email_triage_service -> email_workflow_planner -> email_workflow_service -> agent_skill_selector -> email_agent_client -> runtime`

Core modules:

- `backend/app/services/gmail/gmail_sync_service.py`
- `backend/app/services/gmail/gmail_cache.py`
- `backend/app/services/triage/email_triage_service.py`
- `backend/app/services/workflow/email_workflow_planner.py`
- `backend/app/services/workflow/email_workflow_service.py`
- `backend/app/services/agent/agent_skill_selector.py`
- `backend/app/services/agent/email_agent_client.py`
- `backend/app/services/common/dashboard_status.py`

Primary data files:

- `data/cache/inbox_cache.json`
- `data/cache/email_triage_index.json`
- `data/cache/email_briefs.json`
- `data/state/gmail_sync_state.json`
- `data/profile/*`

## Goals

### Goal 1: Visible decision path per message

The system should surface:

- message `category`
- message `suggested_action`
- whether a workflow matched
- matched `workflow_tag`
- final `skill` used
- whether a brief was produced
- whether fallback was used

### Goal 2: Dashboard shows chain state, not scattered flags

Beyond “cache ok, style ok, contacts ok”, show:

- sync progress
- triage progress
- workflow hit rates
- brief generation
- fallback usage
- messages still mid-pipeline

### Goal 3: Read, reply, and follow-ups reuse the same workflow decision

Avoid:

- read via planner
- reply via separate heuristics
- dashboard guessing again

Fallbacks can stay, but must be labeled fallback, not a hidden parallel primary system.

## Checklist by module

### A. `email_triage_service.py`

Add:

- Clearer “why classified” fields per triage item
- At least matched keywords, rule source, or a short rationale
- Aggregated `category` and `suggested_action` stats consumable by the dashboard
- Explicit handling for `other` or non–high-value workflow candidates

Suggested fields:

- `classification_reason`
- `matched_signals`
- `workflow_candidate`

Outcome:

- Not only “labeled hiring”, but “why hiring”

### B. `email_workflow_planner.py`

Add:

- Explainer fields on planner output
- Why a workflow matched
- Why no workflow matched
- `recommended_skill` and `workflow_tag` exported to upper status layers

Suggested fields:

- `decision_reason`
- `fallback_used`
- `fallback_reason`

Outcome:

- Answer “why `needs_hiring_brief`” and “why nothing specialized matched”

### C. `email_workflow_service.py`

Add:

- Observable events for brief generation
- Distinguish:
  - cache hit
  - cache miss
  - freshly generated
  - skipped
- Record brief type and target thread

Suggested metrics:

- `brief_cache_hits`
- `brief_cache_misses`
- `brief_generated_count`
- `brief_skipped_count`

Outcome:

- Not only that `email_briefs.json` exists, but whether generation ran and hit rates

### D. `agent_skill_selector.py`

Add:

- Whether this turn’s skill came from workflow vs fallback heuristic
- Relationship among bundle, workflow tag, and final skill
- Counts for fallback heuristic use

Suggested fields:

- `skill_selection_source`
  - `workflow`
  - `fallback_heuristic`
  - `default`
- `skill_selection_reason`

Outcome:

- Reduce new silent side paths later

### E. `email_agent_client.py`

Add:

- Structured `pipeline_trace` on chat turn results, covering at least:
  - route result
  - workflow resolution
  - selected skill
  - brief used or not
- Make trace data suitable for dashboard and debug APIs, not only local variables

Suggested structure:

- `pipeline_trace`
  - `tool_bundle`
  - `route_context`
  - `workflow_tag`
  - `selected_skill`
  - `brief_type`
  - `used_fallback`

Outcome:

- Every agent response is traceable through the chain

### F. `dashboard_status.py`

Add:

- Turn scattered readiness into a real pipeline overview
- Surface directly:
  - sync status
  - triage status
  - workflow status
  - brief status
  - memory/setup status
- Distinguish:
  - “file initialized”
  - “content generated”
  - “content usable”

Suggested blocks:

- `pipelineStages`
- `triageMetrics`
- `workflowMetrics`
- `briefMetrics`
- `fallbackMetrics`

Outcome:

- Dashboard as “system chain overview”, not a few disconnected readiness strings

### G. Frontend dashboard

Add:

- Workflow hits and brief status on the page, not only console
- Clear per-stage status:
  - pending
  - running
  - ready
  - degraded
- Minimal but explicit counts

Suggested displays:

- `total messages / triaged / triage completion rate`
- `category` distribution
- `suggested_action` distribution
- workflow hit distribution
- brief cache hits and generation counts
- fallback usage counts

Outcome:

- Users see whether the main path is healthy without reading the console

### H. Logging and event names

Add:

- Unified pipeline event naming
- Avoid mixing “sync”, “triage”, “brief” with free-form prose in different places
- Share event names across console, backend logs, and future metrics

Suggested prefixes:

- `pipeline.sync.*`
- `pipeline.triage.*`
- `pipeline.workflow.*`
- `pipeline.brief.*`
- `pipeline.skill.*`
- `pipeline.reply.*`

Outcome:

- Adding logs, metrics, and alerts without inventing a new naming scheme each time

## Fallbacks worth keeping

These remain reasonable:

- Light keyword heuristic when no workflow matches on `draft_reply`
- Runtime reads thread directly when brief misses
- Partial context when profile data is not ready, with explicit partial-context marking

Requirements:

- Fallback must be recorded explicitly
- Fallback must not hide as a second primary path

## Suggested priority

### First

- Structured “why” for triage, planner, and skill selector
- `pipeline_trace` on `email_agent_client`
- workflow / brief / fallback metrics on `dashboard_status`

After this, the main path is much more explicit.

### Second

- Surface these states in the frontend
- More than console text: readable on the page

After this, workflow management is closer to “visible.”

### Third

- Unify pipeline event naming
- Add latency, failure rate, fallback frequency
- Prepare ops and tuning surfaces

After this, observability is in good shape.

## Ideal end state

After this work, the system should reliably answer:

- Why a message was classified `hiring`, `meeting`, or `customer`
- Why it entered a given workflow
- Why a given skill was chosen
- Whether a brief was used
- Whether fallback ran
- How many end-to-end runs today
- Which workflow types hit most often
- Which step fails or is unstable most

If these still require reading code, the pipeline is not explicit enough and observability is still weak.
