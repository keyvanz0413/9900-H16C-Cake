# Bug Review Query Development Plan

## Current Status Update

Status: **implemented / strongly supported**.

The original plan below was written before the dedicated implementation landed. The current codebase now includes `backend/app/services/review/bug_review_service.py`, an auto-selected `bug-review` skill, and an `EmailAgentClient` fast path that renders a compact bug review summary. The remaining parts of this document should be read as design background and future refinement notes, not as evidence that the feature is still missing.

## 1. Feature Goal

### Pair
**Bug Review Query**

### Example User Inputs
- "Help me check what bugs need to be handled recently."
- "Show me recent bug-related emails."
- "What technical issues should I pay attention to?"
- "Any failing builds or bug reports that need action?"
- "Summarise recent technical problems from my inbox."

### Product Goal
This feature should help a founder or technical team lead quickly understand:

- what bug-related or technical-risk emails appeared recently
- which ones are still unresolved
- which ones are most important to act on
- what the likely next step is

This is **not** a developer debugging assistant.  
It is a **bug-situation-awareness workflow** for inbox management.

The ideal result is a short, decision-oriented overview such as:

> I found 3 bug-related items that may need your attention:  
> 1. Build failure on main branch - high priority  
> 2. User-reported onboarding issue - medium priority  
> 3. Regression warning in recent internal thread - medium priority  
> Would you like a detailed summary, the related thread, or a task-style action list?

---

## 2. Current Codebase Basis

The current codebase does **not** yet have a dedicated bug-review workflow, but it already contains useful foundations that can be reused.

### Existing Strong Foundations

#### A. Email triage layer
Files:
- `backend/app/services/triage/email_triage_service.py`
- `backend/app/services/triage/email_triage_store.py`

Current value:
- already scores and ranks emails
- already exposes `priority_label`, `category`, `suggested_action`, `action_required`, `reply_needed`
- already gives a starting point for "which issues matter most"

Important limitation:
- bug review must not rely only on existing triage `category`
- GitHub / CI / no-reply alerts may be treated as automated notices or lower-value items before bug-specific filtering runs

#### B. Skill and request-routing layer
Files:
- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/agent/agent_skill_selector.py`
- `backend/app/services/agent/agent_request_router.py`
- `backend/app/services/agent/email_agent_client.py`

Current value:
- read-only inbox skills already exist for weekly recap and urgent triage
- the skill selector can auto-select repeatable workflows
- the chat client already supports deterministic skill fast paths for some workflows
- this is the right first entry point for broad bug-review requests

#### C. Workflow planning layer
Files:
- `backend/app/services/workflow/email_workflow_planner.py`
- `backend/app/services/workflow/email_workflow_service.py`

Current value:
- workflow planning already exists for:
  - customer brief
  - hiring brief
  - meeting brief
  - human review
- workflow service already resolves triage item + thread metadata + planner recommendation
- this is the right place to add an optional future bug-specific thread brief

Important limitation:
- current chat flow only resolves `EmailWorkflowService` workflow context for `thread_deep_read` and `draft_reply` turns
- a broad request like "what bugs need to be handled recently" normally routes as `read_only_inbox`
- therefore, adding only `needs_bug_brief` to the planner would not reliably trigger the user-facing feature

#### D. Full thread reading and inbox access
Existing system already supports:
- inbox search
- full thread reading
- recent email retrieval
- sender and subject analysis

This means the feature does **not** need a new data access architecture from scratch.

---

## 3. What Is Missing Right Now

At the moment, bug-related questions can only be handled indirectly using general triage and thread reading. The system is still missing the pieces below.

### Missing Piece 1: Bug review aggregation flow
There is no service that can:
- scan recent inbox and triage data for bug-like items
- dedupe repeated alerts in the same thread
- rank issues by bug-specific urgency and impact
- return a compact summary across multiple emails

### Missing Piece 2: Bug-specific skill definition
There is no current skill such as:
- `bug-review`
- `technical-issue-briefing`

So explicit bug-review requests do not have a dedicated prompt workflow.

### Missing Piece 3: Bug-specific request detection
The skill selector and/or router currently does not recognise broad requests such as:
- bug review
- technical issue summary
- build failure check
- issue status check
- failing tests

### Missing Piece 4: Bug signal extraction
The system does not yet have a clean bug signal layer that can identify patterns such as:
- build failed
- CI failed
- tests failing
- issue opened
- issue reopened
- regression detected
- deployment broken
- integration broken
- error report from user
- outage / incident / crash

### Missing Piece 5: Bug-specific ranking logic
Generic triage ranking exists, but bug review should additionally consider:
- production impact
- demo impact
- investor/client meeting impact
- user-facing breakage
- repeated reports
- critical sender context such as team lead, CI bot, customer, partner

### Missing Piece 6: Optional thread-level bug brief
For one specific bug-like thread, the workflow planner still cannot yet detect:
- build failures
- regression warnings
- issue opened / reopened
- bug escalation emails
- test failures
- user-reported technical problems

This is useful, but it should be treated as a follow-up capability after the broad aggregation flow is in place.

---

## 4. Recommended Feature Scope

To keep the implementation realistic and aligned with the current codebase, the first version should support the following.

### Version 1 Scope
The first complete workflow should answer:

1. What recent bug-related emails exist?
2. Which ones appear unresolved or still actionable?
3. Which ones should be prioritised first?
4. What is the likely next step for each one?

### Version 1 Output Structure
For each detected item:
- short title
- bug type
- source
- current urgency / priority
- unresolved status
- recommended next action

### Example Output Shape
```text
Bug Review Summary

1. Build failure on main branch
- Type: CI / build
- Source: GitHub Actions alert
- Status: unresolved
- Priority: high
- Next step: review failing test thread and assign engineering owner

2. Onboarding issue reported by user
- Type: user-reported product issue
- Source: customer email
- Status: needs confirmation
- Priority: medium
- Next step: read thread and confirm reproduction details
```

### Explicitly Out of Scope for Version 1
Do **not** try to build:
- Jira integration
- GitHub issue sync
- full engineering incident management
- code-level debugging
- automated issue closure
- attachment-based log analysis

The goal is inbox-level issue awareness, not full engineering ops.

---

## 5. Proposed Architecture Change

## 5.1 Create a Bug Review Aggregation Service

### New service recommendation
Create a dedicated backend service:

```text
backend/app/services/review/bug_review_service.py
```

### Why this should come first
The primary Bug Review Query is not about one specific thread. It asks across recent inbox activity:

> "Help me check what bugs need to be handled recently."

That makes it closer to weekly recap / urgent triage than to a single-thread brief.

The current chat flow only resolves thread workflow context for `thread_deep_read` and `draft_reply` turns. A general bug-review request will normally route as `read_only_inbox`, so adding only `needs_bug_brief` to the workflow planner would not reliably trigger the feature.

### Responsibilities
A dedicated service should:
1. fetch recent triage items and inbox cache messages
2. filter bug-like candidates using subject, sender, snippet, triage fields, and thread hints
3. avoid relying only on existing triage `category`, because GitHub / CI / no-reply alerts may be treated as low-value automated notices
4. enrich candidates with lightweight thread metadata where available
5. remove duplicates across the same thread
6. rank final items
7. return a compact bug review summary

### Core methods to implement
Suggested methods:
- `list_bug_candidates(...)`
- `rank_bug_candidates(...)`
- `build_bug_review_summary(...)`

### Input sources
- triage items from `EmailTriageService`
- recent messages from the Gmail cache
- optional thread context from Gmail cache grouping or `EmailWorkflowService`
- contact/sender information where useful

---

## 5.2 Add a New Skill Specification

### File to change
- `backend/app/services/agent/agent_skill_registry.py`

### Add a new skill
Suggested skill name:

```python
"bug-review"
```

### Suggested configuration
- `allowed_bundles`: `("read_only_inbox", "thread_deep_read")`
- `rollout_stage`: start as `"active"` if the service has a deterministic fast path, otherwise `"planned"`
- `auto_select`: `True` for explicit bug-review requests once intent detection and tests are in place

### Suggested prompt intent
The skill should instruct the agent to:
- use the bug review summary flow for broad recent-bug questions
- identify bug-related or technical-risk emails
- summarise issue type, current status, and next step
- focus on unresolved or actionable items
- avoid broad generic inbox summary
- avoid drafting unless the user explicitly asks

### Example prompt direction
- "Use the bug review workflow for this turn."
- "Focus on unresolved technical issues, failing builds, regressions, and user-reported product problems."
- "Return a compact, prioritised issue summary with likely next actions."

---

## 5.3 Add Request Routing / Skill Selection Support

### Files to inspect/update
- `backend/app/services/agent/agent_skill_selector.py`
- `backend/app/services/agent/agent_request_router.py` if a separate route signal is needed
- `backend/app/services/agent/email_agent_client.py` if adding a fast path
- `backend/app/services/agent/email_agent_client_composition.py` if adding prompt policy lines

### Intent signals
Recognise explicit broad bug-review requests such as:
- `bug review`
- `recent bugs`
- `technical issues`
- `build failed`
- `failing tests`
- `regression`
- `CI failed`
- `GitHub Actions`
- `issue opened`
- `what bugs need to be handled`
- Equivalent phrases in Chinese (for multilingual intent detection), e.g. technical issues, build failures, test failures, regressions

### Expected entry behaviour
When user intent is bug review:
1. keep the turn read-only
2. select the `bug-review` skill
3. call `BugReviewService` through a deterministic fast path or a read-only tool
4. return compact prioritised results
5. offer optional follow-ups:
   - summarise bug details
   - open related thread
   - prepare task list
   - draft a reply

---

## 5.4 Add Bug Candidate Filtering and Ranking

### Bug-detection markers
Suggested marker groups:

#### Build / CI markers
- `build failed`
- `ci failed`
- `tests failed`
- `failing tests`
- `pipeline failed`
- `github actions`
- `check suite`
- `failed run`

#### Bug / issue markers
- `bug`
- `issue`
- `incident`
- `regression`
- `broken`
- `error`
- `crash`
- `outage`
- `failure`

#### Product / user complaint markers
- `not working`
- `doesn't work`
- `unable to`
- `cannot access`
- `problem`
- `unexpected`
- `stuck`
- `error message`

### Candidate rule idea
A triage item or cached message should be considered a bug-review candidate when one or more of the following is true:
- its category is already technical-like
- its subject, snippet, or suggested action contains bug markers
- sender appears to be GitHub / CI / engineering bot
- thread metadata suggests repeated technical complaints
- action is required and the content looks issue-oriented

### Suggested ranking factors
- `priority_label`
- `action_required`
- unresolved confidence
- CI/build failure boost
- user-facing issue boost
- sender importance
- repeated issue boost
- production/demo/release impact wording

---

## 5.5 Add Optional Thread-Level Workflow Tag

### File to change
- `backend/app/services/workflow/email_workflow_planner.py`

### Add
Add a new workflow tag:

```python
"needs_bug_brief"
```

### Also add a new brief type:
```python
"bug_brief"
```

### Why this is optional for Version 1
This is useful when the user asks about one specific bug-like thread, for example:

> "Open the GitHub Actions failure thread and explain what happened."

It should not be treated as the main entry point for the broad recent-bug query, because that query is an aggregation workflow.

### Suggested planner result
For a single bug-like thread, return:

```python
EmailWorkflowPlan(
    workflow_tag="needs_bug_brief",
    recommended_skill="bug-review",
    brief_type="bug_brief",
    precompute_priority=...,
    reasons=(...)
)
```

---

## 5.6 Add Optional Bug Brief Generation

### Best architectural location
Use the same brief-generation pattern already used by the workflow service.

### File likely to change
- `backend/app/services/workflow/email_workflow_service.py`
- possibly any brief helper/store used internally

### Required behaviour
Given a triage item + thread context, generate a structured bug brief containing:

- issue title
- issue type
- issue source
- current status
- confidence that it is unresolved
- business impact hint
- recommended next step
- optional evidence lines

### Suggested issue types
Use a lightweight taxonomy:
- `ci_build_failure`
- `test_failure`
- `user_reported_bug`
- `regression_warning`
- `deployment_issue`
- `integration_issue`
- `technical_question`
- `other_issue_signal`

### Suggested status values
- `unresolved`
- `likely_unresolved`
- `awaiting_reply`
- `needs_review`
- `appears_resolved`
- `unknown`

---

## 6. Detailed Implementation Plan

## Step 1: Create aggregation service
### Files
- `backend/app/services/review/bug_review_service.py`

### Tasks
- gather recent triage items and cache messages
- filter bug-related candidates from subject, sender, snippet, and triage fields
- dedupe by thread
- rank by priority, impact, unresolved confidence, and repeated reports
- assemble final summary payload

### Done when
The backend can produce a clean bug overview across multiple items without relying on the agent to manually scan the inbox.

---

## Step 2: Add skill registry entry and selector intent
### Files
- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/agent/agent_skill_selector.py`
- optionally `backend/app/services/agent/agent_request_router.py`

### Tasks
- add `bug-review` skill
- define prompt lines and usage hint lines
- detect explicit bug-review requests while keeping the route read-only
- auto-select the skill once tests prove the intent detection is safe

### Done when
Bug review becomes a first-class skill for broad read-only inbox queries.

---

## Step 3: Add service integration / fast path
### Files
- `backend/app/services/agent/email_agent_client.py`
- `backend/app/services/agent/email_agent_client_composition.py` if prompt policy needs updating
- any API endpoint layer if the frontend calls summaries directly

### Tasks
- recognise the `bug-review` skill
- call `BugReviewService`
- return results in the same style as weekly summary / triage outputs
- add user-facing follow-up suggestions

### Done when
A natural-language bug review request can trigger the correct backend summary flow.

---

## Step 4: Add optional planner support
### Files
- `backend/app/services/workflow/email_workflow_planner.py`

### Tasks
- add `needs_bug_brief`
- add `bug_brief`
- add bug marker detection for single-thread workflow planning
- ensure priority label influences precompute priority

### Done when
A specific bug-like thread can be classified into a bug workflow.

---

## Step 5: Add optional bug brief generation
### Files
- `backend/app/services/workflow/email_workflow_service.py`
- related brief helper/store code if needed

### Tasks
- add support for `bug_brief`
- extract issue type, source, unresolved hints, next step
- keep output deterministic and compact
- ensure thread-level context can override single-email noise

### Done when
A single bug-related thread can produce a structured bug brief.

---

## Step 6: Add tests
### Files to add
- `backend/tests/test_bug_review_service.py`
- skill selector / routing tests
- planner tests if optional planner support is implemented
- workflow service tests if optional bug brief generation is implemented

### Minimum test cases
1. detects CI/build failure email
2. detects user-reported bug email
3. ignores unrelated newsletter
4. dedupes repeated alerts in same thread
5. ranks production/user-facing issue above low-value alert
6. marks unresolved items cautiously when no reply or resolution is visible
7. handles mixed inbox with only one relevant technical issue
8. returns empty but safe summary when no bug signals exist
9. does not miss GitHub / CI / no-reply alerts just because triage classified them as automated or low value

### Done when
Feature is stable enough to demo and refactor safely.

---

## 7. Suggested Data Contract

The final backend summary should return something like:

```json
{
  "summary_title": "Recent bug-related items",
  "total_candidates": 4,
  "top_items": [
    {
      "thread_id": "abc123",
      "title": "Build failure on main branch",
      "issue_type": "ci_build_failure",
      "source": "GitHub Actions",
      "priority_label": "P0_URGENT",
      "status": "unresolved",
      "action_required": true,
      "next_step": "Review failing test thread and assign owner"
    }
  ],
  "follow_up_options": [
    "summarise bug details",
    "open related thread",
    "prepare task list",
    "draft a reply"
  ]
}
```

This keeps the output:
- structured
- testable
- frontend-friendly
- easy to convert into natural language

---

## 8. UI / UX Recommendation

The frontend does not need a special new page in version 1.  
It can use the same chat-based interaction style as existing capabilities.

### Recommended response format
Return:
- headline count
- top 3 issues
- one-line explanation per item
- short follow-up suggestions

### Good UX pattern
> I found 3 bug-related items that may need your attention.  
> The highest-priority one is a build failure affecting the main branch.  
> Would you like a detailed breakdown, the related thread, or a task list?

This is better than dumping raw email text.

---

## 9. Suggested Development Order

### Phase 1
- aggregation service
- bug candidate filtering
- dedupe and ranking
- core service tests

### Phase 2
- `bug-review` skill spec
- selector / route intent detection
- deterministic service integration or fast path
- basic natural-language output

### Phase 3
- optional planner support for specific bug threads
- optional `bug_brief` generation
- workflow service tests if implemented

### Phase 4
Optional improvements:
- distinguish internal bug vs external customer complaint
- better unresolved-status detection
- repeated issue clustering
- demo-impact / production-impact heuristics
- optional frontend presentation polish

---

## 10. Risks and Mitigations

### Risk 1: Too many false positives
Emails containing words like `issue` or `problem` may not be actual bugs.

**Mitigation**
- combine multiple signals
- use sender/source clues
- require stronger evidence for high-priority classification

### Risk 2: Too many duplicates
CI systems may send multiple emails for the same underlying failure.

**Mitigation**
- dedupe by thread
- optionally normalise similar subject lines

### Risk 3: Generic triage and bug workflow overlap too much
If bug review just repeats triage, the feature feels redundant.

**Mitigation**
- focus on technical issue summary
- include issue type, unresolved state, and engineering-style next steps

### Risk 4: Thread status is ambiguous
Sometimes the bug may already be fixed but the inbox does not clearly show closure.

**Mitigation**
- use cautious labels like `likely_unresolved`
- avoid overclaiming resolution state

### Risk 5: CI / GitHub alerts are filtered as low-value automation
Existing triage may treat no-reply or automated alert senders as noise.

**Mitigation**
- let `BugReviewService` scan subject, sender, and snippet directly
- add positive boosts for GitHub Actions, CI, test failure, deployment, and incident markers
- test no-reply CI alerts explicitly

---

## 11. Definition of Done

This feature can be considered complete for version 1 when:

- a bug-related user request is correctly routed or skill-selected
- bug-like candidate emails are detected from recent inbox content
- unrelated emails are mostly filtered out
- duplicate alerts are reduced
- each top item includes:
  - issue title
  - issue type
  - status
  - priority
  - next step
- there are automated tests covering the main cases
- the output is concise enough for founder-style inbox review

Optional thread-level work is complete when:
- a specific bug-like thread can be classified as `needs_bug_brief`
- `bug_brief` can be generated and rendered into prompt lines

---

## 12. Recommended File Change List

### New file
- `backend/app/services/review/bug_review_service.py`
- `backend/tests/test_bug_review_service.py`

### Existing files likely to change for Version 1
- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/agent/agent_skill_selector.py`
- `backend/app/services/agent/email_agent_client.py`
- `backend/app/services/agent/email_agent_client_composition.py` if adding bundle/skill policy lines
- `backend/tests/test_email_workflow_planner.py` only if planner support is included now

### Optional follow-up files
- `backend/app/services/workflow/email_workflow_planner.py`
- `backend/app/services/workflow/email_workflow_service.py`
- workflow service tests for `bug_brief`

---

## 13. Short Developer Summary

To build **Bug Review Query** properly on top of the current codebase:

1. create `BugReviewService` for cross-email aggregation first
2. detect bug-like candidates using direct inbox/cache text plus triage fields, not triage category alone
3. dedupe and rank bug candidates with CI/build, user-facing, unresolved, and sender-impact signals
4. add a `bug-review` skill and auto-select it for explicit broad bug-review requests
5. expose the service through the normal read-only chat flow or a deterministic skill fast path
6. add tests for CI alerts, user bug reports, no-reply bot alerts, false positives, dedupe, and empty results
7. optionally add `needs_bug_brief` / `bug_brief` later for one specific bug-like thread

This approach fits the current architecture and avoids building a parallel system from scratch, while also avoiding the main trap: adding only a thread-level workflow tag for a query that is actually a cross-inbox aggregation task.
