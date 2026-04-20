# Personalized Email Workflow Plan

This document answers one question:

**How to evolve the “email triage funnel” in the current project into an agent workflow that better matches user habits.**

The goal is not to make the system larger, but to have the agent default to decisions that fit the user per scenario, instead of only dumping the raw message on them.

## Core Conclusion

The project already has two strong foundations:

- A unified email triage funnel
  - `EmailTriageService` produces `category`, `priority_label`, and `suggested_action`
- A pipeline that picks a bundle by task, then a skill inside the bundle
  - `route -> tool bundle -> active skill -> tool`

The next best step is not rewriting the agent, but adding one layer:

**Funnel result + user profile + current context → workflow tag → matching skill → pre-generated brief**

In one sentence:

**Do not only answer “what kind of email is this,” but “what this email means for this user.”**

---

## What the Code Already Has

### 1. Email funnel

The funnel already outputs:

- `category`
- `priority_label`
- `priority_score`
- `reasons`
- `suggested_action`

Rough categories include:

- `meeting`
- `reply_needed`
- `project_update`
- `finance`
- `security`
- `newsletter`
- `notification`
- `personal`
- `other`

Relevant code:

- `backend/app/services/triage/email_triage_service.py`

This layer is a good entry point for “smarter workflows” without a rewrite.

### 2. Route / bundle / skill

The chat side already has clear layers:

- `AgentRequestRouter`
  - Decides which request class this turn belongs to
- `tool bundle`
  - Decides which tools the agent can see
- `AgentSkillSelector`
  - Activates a more specific skill workflow inside the bundle

There are only five bundles today:

- `read_only_inbox`
- `thread_deep_read`
- `draft_reply`
- `mailbox_action`
- `contact_or_crm`

Relevant code:

- `backend/app/services/agent/agent_request_router.py`
- `backend/app/services/agent/agent_skill_selector.py`
- `backend/app/services/agent/agent_skill_registry.py`
- `agents/email-agent/runtime/tool_bundles.py`

### 3. User preference learning (early shape)

The project already has a good precedent:

- On first init, learn `writing_style.md` from `sent` mail
- Refresh style from confirmed sends and explicit feedback

Relevant code:

- `agents/email-agent/tools/style.py`

This shows an accepted pattern:

- Bootstrap from history
- Refine from real use and feedback

Later, “reading habits / decision preferences” should follow the same idea.

---

## Plan Overview

Keep new pieces to four small modules—do not do too much at once.

### 1. `user_profile`

Purpose:

- Store stable preferences
- Describe “who this user is, what they care about, default result shape”

Start with a simple file:

- `data/user_profile.json`

Suggested fields:

```json
{
  "role": "startup_ceo",
  "priorities": ["hiring", "customers", "fundraising"],
  "default_view": "decision_brief",
  "brief_preferences": {
    "prefer_short_summary_first": true,
    "prefer_risk_and_next_step": true
  }
}
```

This is not chat history; it is long-term preference.

### 2. `workflow_tag`

Purpose:

- Not only label email content
- Also label “how it should be handled”

Do not stop at:

- `job_application`
- `meeting`
- `finance`

Add another layer:

- `needs_candidate_brief`
- `needs_meeting_brief`
- `needs_reply_draft`
- `needs_cleanup`
- `needs_human_review`

Then skill selection is driven by “what this user needs as output,” not only “email type.”

### 3. `brief_generator`

Purpose:

- Produce structured briefs per workflow
- Let users see a tailored summary first, then drill into body, attachments, thread

Outputs should be:

- `candidate_brief`
- `meeting_brief`
- `finance_brief`
- `customer_brief`

Not a single generic “email summary.”

### 4. `preference_learner`

Purpose:

- Learn preferences from real behavior
- Update `user_profile` or `learned_patterns`

Signals can include:

- Which sections users always expand
- Which extra info they always ask for
- What they often ignore
- Format patterns they repeat

Note:

- Learn only from stable, repeated behavior
- Do not learn long-term preferences from one-off task details

---

## Recommended Flow

Keep the flow simple:

```text
Email sync
-> Unified funnel produces category / priority / suggested_action
-> From triage + user_profile generate workflow_tag
-> High-value workflow hits enter the matching skill
-> Generate and cache brief
-> User views brief
-> Behavior and feedback feed preference learner
-> Gradually update user_profile / learned_patterns
```

The important boundaries:

- Funnel handles “the email itself”
- User profile handles “this user”
- Workflow tag handles “which workflow to enter”
- Skill handles “what this scenario should produce”

---

## Two Examples

### Example 1: CEO reading job applications

Email characteristics:

- Job-seeking tone
- Resume / cover letter / portfolio
- Clear role application

Funnel might output:

- `category = other` or later `job_application`
- `priority_label = P1_ACTION_NEEDED`
- `suggested_action = review_now`

With user profile:

- `role = startup_ceo`
- `default_view = decision_brief`
- `priorities` includes `hiring`

Final workflow tag:

- `needs_candidate_brief`

Skill output should not be only:

- “Here is a job application; attachments include resume and cover letter”

It should be:

- Who the candidate is
- Highlights
- Portfolio highlights worth attention
- Fit for the role
- Risks
- Suggested next step

Users can open raw resume and work samples if needed.

### Example 2: Founder reading customer issue emails

Email characteristics:

- Customer asks about bug / launch time / urgent issue
- Long thread
- Clear action request

Funnel might output:

- `category = reply_needed` or `project_update`
- `priority_label = P0_URGENT`
- `suggested_action = review_and_reply`

If user profile has:

- `role = founder`
- `priorities` includes `customers`
- `prefer_short_summary_first = true`

Final workflow tag:

- `needs_customer_brief`

Skill should prioritize:

- Who the customer is
- Where things are blocked
- What they want from you
- Deadline / risk
- Suggested reply direction

Not making the user mine a long thread for the point.

---

## How to Wire Into Current Code

### Layer 1: Keep the funnel; do not rewrite

Continue using:

- `backend/app/services/triage/email_triage_service.py`

Add only a few fields if needed, e.g.:

- `workflow_hints`
- `entity_tags`
- `brief_type`

Do not turn triage into a giant “smart hub.”

### Layer 2: Add a light `workflow planner`

Add a service, e.g.:

- `backend/app/services/workflow/email_workflow_planner.py`

Single responsibility:

- From `triage result + user_profile + thread context` produce:
  - `workflow_tag`
  - `recommended_skill`
  - `brief_type`

This layer should not draft mail or read/write actions directly.

### Layer 3: Add read-only skills first

First skills should be briefing-style, not action-style:

- `candidate-briefing`
- `customer-briefing`
- `meeting-briefing`

Raise “smartness” without complicating send, archive, or CRM writes.

Prefer existing bundles:

- Most brief skills on `thread_deep_read`
- A few overview skills on `read_only_inbox`

### Layer 4: Cache brief results

Add a light cache file, e.g.:

- `data/email_briefs.json`

Purposes:

- Precompute in background
- Instant open when the user views
- Avoid re-analyzing the same message every time

Suggested cache keys:

- `message_id`
- `thread_id`
- `workflow_tag`
- `brief_type`
- `generated_at`

### Layer 5: Learn from behavior

Add a light file, e.g.:

- `data/learned_patterns.json`

Purpose:

- Store recurring preferences

Examples:

- CEO always opens `role_fit` first
- Founder always opens `action_items` first
- Some users always want “three-line conclusion first”

Do not over-automate at first.

Simplest approach:

- Log behavior first
- Update `user_profile` only after thresholds

---

## Why This Stays Manageable

Because it does not require right now:

- Vector database
- Multi-agent orchestration
- A large system per email type
- Generic memory platform migration

This upgrades the system from:

- `Email classification -> user asks -> agent answers ad hoc`

To:

- `Email classification -> workflow tag -> matching skill pre-generates brief -> user consumes`

Complexity concentrates in “workflow planner” and “brief generator”; overall structure stays familiar.

---

## Adding a New Email Type and Flow Later

Use these six steps to avoid drift:

### 1. Define the outcome the user actually needs

Do not start with “what email is this”; start with:

- What decision the user makes when they see this type

Examples:

- Job application → whether to advance the candidate
- Escalated customer complaint → whether to act immediately and who owns it
- Investor email → whether to prioritize a reply

### 2. Define `workflow_tag`

Examples:

- `needs_candidate_brief`
- `needs_customer_escalation_brief`
- `needs_investor_brief`

Do not embed business logic only inside skills.

### 3. Pick which bundle it belongs to

Default rule:

- Read-only analysis → `read_only_inbox` or `thread_deep_read`
- Real actions → `draft_reply` or `mailbox_action` only when needed

### 4. Add a skill

In:

- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/agent/agent_skill_selector.py`

Add the new skill and selection rules.

### 5. Define a brief template

Each new workflow should have a fixed output shape.

Example `candidate-briefing`:

- Snapshot
- Highlights
- Role fit
- Risks
- Recommended next step

### 6. Add tools only if needed

Ask:

- Whether search, thread, contacts, and attachment tools are enough

If yes, do not add tools.

Add tools only when existing tools cannot retrieve key evidence.

---

## Suggested Implementation Order

Follow this order; avoid parallel sprawl:

1. Add `user_profile.json`
2. Add `email_workflow_planner.py`
3. Implement one briefing skill first
   - Recommended: `candidate-briefing`
4. Add `email_briefs.json` cache
5. Add `learned_patterns.json` last

This ships one full path before expanding.

---

## End Goal

The end state is not:

- “The agent can read email”

But:

- The agent knows what this email means for this user
- Which workflow to enter
- What to show first

That is “smarter,” and the right evolution path for this project.
