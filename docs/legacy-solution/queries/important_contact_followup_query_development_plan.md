# Important Contact Follow-Up Query Development Plan

## 1. Feature Goal

### Pair
**Important Contact Follow-Up Query**

### Example User Inputs
- “Which important contacts should I proactively keep in touch with recently?”
- “Who should I follow up with?”
- “Any high-priority contacts I haven’t replied to recently?”
- “Which important relationships are going quiet?”
- “Show me key contacts that may need a proactive check-in.”

### Product Goal
This feature should help a founder or relationship owner quickly understand:

- which important contacts have gone quiet recently
- which relationships may need proactive maintenance
- where follow-up is recommended even if no one explicitly asked again
- which follow-ups matter most from a business or relationship perspective
- what the likely next action is

This is **not** a full CRM system.  
It is a **relationship-maintenance and proactive follow-up workflow** built on top of inbox activity.

The ideal result is a short, prioritised overview such as:

> “There are 3 important contacts you may want to reconnect with:  
> 1. Investor A — no follow-up sent after the recent meeting  
> 2. Recruiter B — last interaction was over a week ago  
> 3. Client C — the thread has gone quiet after a proposal discussion  
> Would you like me to draft a follow-up message, summarise the relationship history, or rank them by importance?”

---

## 2. Current Codebase Basis

The current codebase already has several strong foundations for this feature, but they are not yet combined into a dedicated important-contact follow-up workflow.

### Existing Strong Foundations

#### A. Follow-up detection layer
File:
- `backend/app/services/workflow/follow_up_service.py`

Current value:
- already analyses thread-level follow-up status
- already reasons about whether a thread is awaiting reply
- already helps detect stalled conversations
- provides the strongest base for this feature

#### B. Contact repository / importance layer
Files:
- contact repository / contacts-related modules
- `contacts.csv` or `contacts.json` data path references where applicable
- planner / triage contact-aware logic

Current value:
- contact identity and sender importance already exist in the system
- enables distinction between high-value contacts and normal senders
- useful for investor / client / recruiter / collaborator weighting

#### C. Email triage layer
Files:
- `backend/app/services/triage/email_triage_service.py`
- `backend/app/services/triage/email_triage_store.py`

Current value:
- already provides:
  - priority labels
  - action-required signals
  - suggested actions
  - thread-linked prioritisation
- useful for deciding which contacts matter more right now

#### D. Thread-level workflow resolution
File:
- `backend/app/services/workflow/email_workflow_service.py`

Current value:
- already combines thread data, planning, and triage
- suitable for generating short relationship-status briefs
- already operates at the right architectural level for follow-up reasoning

#### E. Planned important-contact skill direction
File:
- `backend/app/services/agent/agent_skill_registry.py`

Current value:
- there are already hints that important-contact style workflow is intended
- the architecture already supports planned skills becoming first-class workflows

---

## 3. What Is Missing Right Now

At the moment, the system can detect some follow-up signals, but it does not yet provide a dedicated important-contact follow-up experience.

### Missing Piece 1: Important-contact-specific workflow routing
The current system can detect:
- some stalled threads
- some unanswered threads
- some follow-up candidates

But it does not yet answer:
- which *important* contacts deserve proactive outreach
- which follow-ups are about relationship maintenance rather than simple pending replies
- which quiet relationships should be prioritised

### Missing Piece 2: Contact importance + follow-up fusion
You already have both sides separately:
- contact importance
- thread follow-up state

What is missing is the dedicated logic that combines them into:
- “important person + quiet interaction + worth reconnecting”

### Missing Piece 3: Relationship-maintenance heuristics
This feature needs more than “awaiting reply.”  
It should also detect situations like:
- recent meeting happened but no follow-up sent
- warm thread went quiet after meaningful progress
- high-priority external contact has not been engaged for too long
- proposal / recruiting / client / investor thread needs proactive touchpoint

### Missing Piece 4: Important contact brief generation
There is no standard brief yet that clearly states:
- who the contact is
- why they matter
- last meaningful interaction
- why follow-up is recommended
- what kind of outreach is suitable

### Missing Piece 5: Aggregation across multiple contacts
This feature should not answer only one thread.  
It should scan recent relationship patterns and produce:
- a shortlist of key contacts
- why each is being surfaced
- which one should come first

### Missing Piece 6: User-facing request path
There is no explicit request route yet for:
- key contacts to reconnect with
- important relationships going quiet
- proactive follow-up suggestions

---

## 4. Recommended Feature Scope

To keep implementation realistic and aligned with the current architecture, version 1 should focus on inbox-based relationship maintenance.

### Version 1 Scope
The first complete workflow should answer:

1. Which important contacts have had no recent meaningful follow-up?
2. Which threads involving those contacts appear stalled or quiet?
3. Which contacts are most worth reconnecting with now?
4. What is the likely best next action for each one?

### Version 1 Output Structure
For each surfaced contact:
- contact name
- relationship type
- importance level
- last meaningful interaction hint
- why follow-up is recommended
- recommended outreach type
- optional thread reference

### Example Output Shape
```text
Important Contact Follow-Up Summary

1. Investor A
- Relationship: investor
- Last interaction: meeting discussion last week
- Signal: no follow-up after confirmed discussion
- Priority: high
- Next step: send concise update and keep momentum

2. Recruiter B
- Relationship: recruiter
- Last interaction: candidate discussion 8 days ago
- Signal: thread has gone quiet
- Priority: medium
- Next step: send short check-in message
```

### Explicitly Out of Scope for Version 1
Do **not** try to build:
- a full CRM timeline system
- automatic campaign reminders
- calendar-driven relationship scheduling
- contact enrichment from external tools
- long-term contact scoring dashboards

The goal is proactive inbox follow-up suggestions, not a standalone relationship platform.

---

## 5. Proposed Architecture Change

## 5.1 Add or Formalise Important-Contact Workflow Tag

### File to inspect/change
- `backend/app/services/workflow/email_workflow_planner.py`

### Recommended direction
Add or stabilise a workflow tag such as:

```python
"needs_important_contact_followup"
```

Or, if you want to stay closer to existing naming conventions:

```python
"needs_contact_followup_brief"
```

### Suggested brief type
```python
"important_contact_followup_brief"
```

### Why
This feature is distinct from generic “awaiting reply” because it combines:
- relationship importance
- interaction gap
- proactive business-value follow-up

---

## 5.2 Add or Activate a Dedicated Skill Specification

### File to change
- `backend/app/services/agent/agent_skill_registry.py`

### Add or formalise a skill
Suggested skill name:

```python
"important-contact-followup"
```

If the registry already has something similar, formalise and activate it rather than creating a parallel skill.

### Suggested configuration
- `allowed_bundles`: likely `("thread_deep_read", "read_only_inbox")`
- `rollout_stage`: may begin as `"planned"`
- `auto_select`: `False` initially, enable after stability

### Suggested prompt intent
The skill should instruct the agent to:
- identify important contacts who may need proactive follow-up
- focus on relationship maintenance, not only pending replies
- explain why each contact is being surfaced
- suggest lightweight next-step outreach
- avoid sounding like a CRM export

### Example prompt direction
- “Use the important contact follow-up workflow for this turn.”
- “Prioritise investors, clients, recruiters, and key collaborators when follow-up is justified.”
- “Return a concise founder-friendly shortlist with reasons and next steps.”

---

## 5.3 Extend Workflow Planning Logic

### File to change
- `backend/app/services/workflow/email_workflow_planner.py`

### Add follow-up / relationship markers
Suggested marker groups:

#### Follow-up markers
- `follow up`
- `checking in`
- `circling back`
- `just following up`
- `any updates`
- `let me know`
- `keep in touch`

#### Relationship-progress markers
- `great meeting`
- `good to connect`
- `proposal`
- `next steps`
- `deck`
- `traction`
- `candidate update`
- `partnership`
- `intro`

#### Important sender types
These are not text markers only. Also use sender/contact classification:
- investor
- client
- recruiter
- collaborator
- advisor
- founder ecosystem contact

### Planning rule idea
A thread/contact should be considered an important follow-up candidate when:
- the contact is classified as high priority
- the thread had meaningful recent interaction
- there is currently no strong recent outbound follow-up
- the thread is quiet or stalled
- a proactive check-in is likely valuable

### Suggested planner result
Return something like:

```python
EmailWorkflowPlan(
    workflow_tag="needs_important_contact_followup",
    recommended_skill="important-contact-followup",
    brief_type="important_contact_followup_brief",
    precompute_priority=...,
    reasons=(...)
)
```

---

## 5.4 Add Important Contact Brief Generation

### Best architectural location
Use the same brief-generation pattern already used by the workflow service.

### File likely to change
- `backend/app/services/workflow/email_workflow_service.py`
- related helper/store code if needed

### Required behaviour
Given a thread/contact context, generate a structured follow-up brief containing:

- contact name
- relationship type
- why the contact matters
- last meaningful interaction
- why follow-up is recommended now
- whether the thread is awaiting reply vs simply quiet
- suggested outreach style
- recommended next step

### Suggested relationship types
- `investor`
- `client`
- `recruiter`
- `candidate`
- `collaborator`
- `advisor`
- `internal_key_contact`
- `unknown`

### Suggested status values
- `followup_recommended`
- `awaiting_reply`
- `quiet_but_valuable`
- `recently_active_no_action`
- `not_enough_signal`
- `unknown`

### Suggested next-step values
- `send_short_checkin`
- `send_update`
- `draft_followup`
- `review_thread_first`
- `no_action`

---

## 5.5 Add a Dedicated Aggregation Service

### New service recommendation
Create a dedicated backend service:

```text
backend/app/services/important_contact_followup_service.py
```

### Why a separate service is recommended
This feature is an **aggregation workflow** across multiple contacts and threads.

A dedicated service should:
1. fetch recent triage items and/or follow-up candidates
2. enrich them with contact importance
3. identify relationship-maintenance opportunities
4. dedupe multiple threads for the same contact where needed
5. rank the most valuable follow-up targets
6. return a compact shortlist

### Core methods to implement
Suggested methods:
- `list_followup_contact_candidates(...)`
- `score_relationship_followup(...)`
- `build_contact_followup_brief(...)`
- `build_important_contact_summary(...)`

### Input sources
- follow-up signals from `FollowUpService`
- triage items from `EmailTriageService`
- thread context from `EmailWorkflowService`
- contact metadata / importance data

---

## 5.6 Add Contact-Scoring Heuristics

### Why this is needed
Generic follow-up detection alone is not enough.  
The feature must distinguish:
- a random unanswered thread
from
- an important relationship that should not go cold

### Suggested scoring factors
- contact importance level
- sender type (investor > client > recruiter > generic)
- recency of last meaningful exchange
- whether a meeting or proposal happened recently
- whether the latest user message was outbound with no response
- whether the thread had strong business signals
- whether there is already another active recent thread with the same contact

### Example heuristic outcomes
- investor after meeting but no follow-up → strong boost
- recruiter thread quiet for 8 days → medium boost
- random newsletter sender → filtered out
- low-importance unanswered thread → low or none

---

## 5.7 Add a User-Facing Entry Point

### Where to wire it
Depending on your current request-routing flow, add intent recognition for:
- who should I follow up with
- important contacts to reconnect with
- key relationships going quiet
- proactive contact suggestions

### Likely files to inspect/update
- request router / intent routing layer
- main email agent client integration layer
- any summary feature endpoint layer already used for triage or weekly summary

### Expected entry behaviour
When user intent is important contact follow-up:
1. route to important-contact follow-up summary flow
2. call `ImportantContactFollowupService`
3. return prioritised relationship-maintenance suggestions
4. offer optional follow-ups:
   - draft message
   - open thread
   - show recent interaction summary
   - rank by importance

---

## 6. Detailed Implementation Plan

## Step 1: Stabilise planner support
### Files
- `backend/app/services/workflow/email_workflow_planner.py`

### Tasks
- add or formalise important-contact follow-up workflow tag
- add relationship/follow-up markers
- combine contact importance with quiet-thread signals
- improve planner reasons for why a contact is surfaced

### Done when
A strong important-contact candidate can be reliably classified into the correct workflow.

---

## Step 2: Add skill registry entry
### Files
- `backend/app/services/agent/agent_skill_registry.py`

### Tasks
- add or formalise `important-contact-followup`
- define prompt lines
- define output expectations
- begin with planned rollout if needed

### Done when
Important contact follow-up becomes a first-class workflow option in the skill model.

---

## Step 3: Add brief generation
### Files
- `backend/app/services/workflow/email_workflow_service.py`
- related helper/store code if needed

### Tasks
- add support for `important_contact_followup_brief`
- extract relationship type, last interaction, follow-up reason, next step
- distinguish “awaiting reply” from “proactive reconnection recommended”
- keep output concise and founder-friendly

### Done when
A single high-value contact/thread can produce a structured follow-up brief.

---

## Step 4: Build aggregation service
### Files
- `backend/app/services/important_contact_followup_service.py`

### Tasks
- gather follow-up candidates
- enrich with contact importance
- dedupe by contact when useful
- score and rank candidates
- assemble final shortlist payload

### Suggested ranking factors
- contact importance
- business-value signal
- interaction gap length
- meeting/proposal follow-up boost
- awaiting-reply status
- recency
- thread importance / triage score

### Done when
The backend can produce a clean shortlist of key contacts worth reconnecting with.

---

## Step 5: Add API/service integration
### Files
- request routing layer
- main email agent client integration layer
- any summary feature endpoint layer

### Tasks
- recognise important-contact-follow-up intent
- call `ImportantContactFollowupService`
- return concise shortlist output
- add user-facing follow-up suggestions

### Done when
A natural-language request about key contacts to reconnect with triggers the correct workflow.

---

## Step 6: Add tests
### Files to add
- `backend/tests/test_important_contact_followup_service.py`
- planner tests
- workflow service tests if needed

### Minimum test cases
1. surfaces investor after recent meaningful thread goes quiet
2. surfaces recruiter after candidate discussion stalls
3. ignores low-value unanswered thread
4. distinguishes awaiting reply from proactive reconnect case
5. dedupes multiple threads for same contact when appropriate
6. ranks investor/client follow-up above low-priority contact
7. returns empty but safe summary when no follow-up candidates exist
8. supports “draft message” style follow-up option correctly

### Done when
Feature is stable enough to demo and refactor safely.

---

## 7. Suggested Data Contract

The final backend summary should return something like:

```json
{
  "summary_title": "Important contacts worth following up with",
  "total_contacts": 3,
  "top_items": [
    {
      "contact_id": "contact_123",
      "contact_name": "Investor A",
      "relationship_type": "investor",
      "importance_level": "high",
      "last_interaction_hint": "meeting discussion last week",
      "status": "followup_recommended",
      "reason": "No proactive follow-up was sent after a meaningful conversation.",
      "next_step": "Send concise update"
    }
  ],
  "follow_up_options": [
    "draft follow-up message",
    "open related thread",
    "show interaction summary",
    "rank by importance"
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

The frontend does not need a separate page in version 1.  
This feature can use the same chat-based interaction model as other inbox workflows.

### Recommended response format
Return:
- total count of recommended contacts
- top 3 contacts
- one-line reason for each
- short follow-up options

### Good UX pattern
> “There are 3 important contacts you may want to reconnect with.  
> The highest-priority one is Investor A because there was a meaningful exchange last week but no follow-up after it.  
> Would you like a drafted check-in, the related thread, or a ranking by importance?”

This is better than dumping raw thread history.

---

## 9. Suggested Development Order

### Phase 1
- planner support hardening
- skill spec
- contact-importance + follow-up candidate filtering

### Phase 2
- follow-up brief generation
- aggregation service
- ranking heuristics

### Phase 3
- request routing
- frontend integration
- test hardening

### Phase 4
Optional improvements:
- better relationship-stage inference
- contact-level history summarisation
- smarter dedupe across multiple active threads
- calendar signal integration for post-meeting follow-up boosts

---

## 10. Risks and Mitigations

### Risk 1: Too many false positives
Many unanswered emails are not worth proactive follow-up.

**Mitigation**
- require both contact importance and meaningful interaction evidence
- rank relationship-maintenance cases above generic unanswered threads

### Risk 2: Overlap with awaiting-reply feature
This feature may feel too similar to blocked-by-others / follow-up detection.

**Mitigation**
- emphasise proactive relationship maintenance
- surface “quiet but valuable” contacts, not only pending replies
- include relationship-based explanations

### Risk 3: Duplicate contacts across threads
The same person may appear in several recent threads.

**Mitigation**
- dedupe by contact identity when confidence is high
- keep the strongest or most recent meaningful thread

### Risk 4: Weak contact metadata
Some contacts may not yet have good relationship classification.

**Mitigation**
- fall back to sender/domain/context clues
- use cautious labels like `unknown` when needed

---

## 11. Definition of Done

This feature can be considered complete for version 1 when:

- an important-contact follow-up request is correctly routed
- high-value contacts are identified from inbox activity
- quiet or stalled but valuable relationships are surfaced
- low-value unanswered noise is mostly filtered out
- each top item includes:
  - contact name
  - relationship type
  - reason for follow-up
  - status
  - next step
- automated tests cover the main cases
- the output is concise enough for founder-style inbox review

---

## 12. Recommended File Change List

### New file
- `backend/app/services/important_contact_followup_service.py`

### Existing files likely to change
- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/workflow/email_workflow_planner.py`
- `backend/app/services/workflow/email_workflow_service.py`
- contact metadata / enrichment layer if needed
- request routing / feature integration files
- backend tests for planner and workflow integration

---

## 13. Short Developer Summary

To build **Important Contact Follow-Up Query** properly on top of the current codebase:

1. add or formalise an important-contact follow-up workflow tag
2. add or activate an `important-contact-followup` skill
3. teach the planner how to combine contact importance with quiet/stalled thread signals
4. generate structured follow-up briefs from thread and contact context
5. aggregate and rank follow-up candidates in a dedicated service
6. expose it through the standard request flow
7. test it with investor, recruiter, client, and low-value noise cases

This approach fits the current architecture and avoids building a full CRM system from scratch.
