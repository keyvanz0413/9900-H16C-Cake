# Draft Reply Strategy Query Development Plan

## Current Status Update

Status: **strongly supported through the existing draft workflow**.

The current codebase supports the practical user outcome through thread-aware reply drafting, writing-style loading, draft review, and send confirmation. It does not yet expose a separate dedicated `reply-strategy` service, so the plan below remains useful if the team wants a standalone strategy-only workflow. For the current 10-pair evaluation set, this pair can be treated as supported by the existing draft reply pipeline.

## 1. Feature Goal

### Pair
**Draft Reply Strategy Query**

### Example User Inputs
- “How should I respond to this email?”
- “What’s the best way to reply?”
- “Give me a reply strategy before drafting.”
- “What tone and key points should I use here?”
- “Should I answer briefly, or send a fuller response?”

### Product Goal
This feature should help a founder or busy operator quickly understand:

- what the reply should try to achieve
- what tone is most appropriate
- which key points must be included
- whether the message should be short, detailed, deferential, proactive, or neutral
- whether it is better to reply now, ask a question, propose a meeting, send materials, or keep it brief

This is **not** just generic email drafting.  
It is a **reply-strategy and response-planning workflow** that sits *before* draft generation.

The ideal result is a compact strategy such as:

> “A good reply strategy here would be:  
> - tone: warm and professional  
> - goal: acknowledge the request and move the thread forward  
> - include: a short update, one clear answer, and a concrete next step  
> - recommended format: brief reply, no need for a long explanation  
> Would you like me to turn that into a polished draft?”

---

## 2. Current Codebase Basis

The current codebase already has strong foundations for this feature, but they are currently oriented more toward direct drafting than explicit strategy generation.

### Existing Strong Foundations

#### A. Drafting / reply generation workflow
Existing system already supports draft-oriented email help through:
- thread-aware drafting
- response generation
- draft refinement / review flows
- email-agent client orchestration

Current value:
- the ability to generate replies already exists
- this is the strongest base for a strategy layer that runs before drafting

#### B. Writing style layer
Files:
- style-related tooling such as `style.py`
- stored style profile such as `writing_style.md`

Current value:
- already supports adapting output to the user’s preferred tone and communication style
- useful for strategy decisions such as concise vs warm vs formal vs proactive

#### C. Thread-level workflow resolution
File:
- `backend/app/services/workflow/email_workflow_service.py`

Current value:
- already merges thread context, triage, and planner logic
- already supports brief-style outputs
- ideal place to add reply-strategy brief generation

#### D. Email triage layer
Files:
- `backend/app/services/triage/email_triage_service.py`
- `backend/app/services/triage/email_triage_store.py`

Current value:
- already provides signals such as:
  - priority
  - action_required
  - reply_needed
  - suggested_action
- useful for determining whether a reply should be:
  - immediate
  - short
  - deferential
  - proactive
  - optional

#### E. Existing workflow planning architecture
Files:
- `backend/app/services/workflow/email_workflow_planner.py`
- `backend/app/services/agent/agent_skill_registry.py`

Current value:
- current architecture already supports multiple specialised workflows
- makes it natural to add a dedicated “reply strategy” workflow separate from full draft generation

---

## 3. What Is Missing Right Now

At the moment, the system can often help draft a reply, but it does not yet consistently provide a structured answer to:
- how should I respond?
- what tone should I use?
- what should I include?
- should I keep this short or give more detail?

### Missing Piece 1: Strategy-specific workflow routing
The current system leans toward:
- drafting directly
- reviewing existing drafts
- style-aware reply generation

But it does not yet clearly distinguish:
- strategy request
from
- full draft request

### Missing Piece 2: Reply-goal extraction
This feature needs a layer that identifies the best reply goal, such as:
- acknowledge
- confirm
- clarify
- decline
- delay
- propose a meeting
- send materials
- move the thread forward politely

### Missing Piece 3: Tone recommendation logic
The system needs a dedicated strategy layer that determines:
- concise vs detailed
- warm vs formal
- proactive vs neutral
- deferential vs direct

based on:
- sender relationship
- urgency
- current thread tone
- user style profile

### Missing Piece 4: Key-point extraction
There is no standard brief yet that states:
- what must be included
- what can be omitted
- whether the reply needs:
  - one concrete answer
  - a status update
  - a meeting proposal
  - an attachment mention
  - a polite boundary or decline

### Missing Piece 5: Reply-length and reply-shape recommendation
This feature should help answer:
- short reply or full explanation?
- reply now or later?
- answer directly or move to call/meeting?
- one paragraph or several bullets?

### Missing Piece 6: User-facing strategy path
There is no explicit workflow yet for:
- reply strategy
- how should I answer
- tone and key points before drafting

---

## 4. Recommended Feature Scope

To keep implementation realistic and aligned with the current architecture, version 1 should focus on strategy-first reply guidance.

### Version 1 Scope
The first complete workflow should answer:

1. What is the best reply goal for this email?
2. What tone should be used?
3. What key points should be included?
4. How long or detailed should the response be?
5. What is the recommended next action?
6. Optionally, should the system generate a draft next?

### Version 1 Output Structure
For each reply-strategy result:
- reply goal
- recommended tone
- recommended reply length / style
- key points to include
- optional caution or boundary note
- recommended next action
- optional draft offer

### Example Output Shape
```text
Reply Strategy Summary

- Goal: acknowledge the request and provide a concrete next step
- Tone: warm and professional
- Length: short reply
- Include:
  1. brief acknowledgement
  2. one clear answer
  3. proposed next step
- Next action: turn into polished draft
```

### Explicitly Out of Scope for Version 1
Do **not** try to build:
- a full rhetorical analysis engine
- persuasive writing scoring
- automatic legal/compliance advice
- multi-message reply simulation
- deep personality modelling beyond current style profile

The goal is practical response planning, not advanced communication coaching.

---

## 5. Proposed Architecture Change

## 5.1 Add or Formalise Reply Strategy Workflow Tag

### File to inspect/change
- `backend/app/services/workflow/email_workflow_planner.py`

### Recommended direction
Add or stabilise a workflow tag such as:

```python
"needs_reply_strategy_brief"
```

### Suggested brief type
```python
"reply_strategy_brief"
```

### Why
This feature is distinct from:
- generic drafting
- style adaptation only
- urgency detection
- follow-up detection

It specifically focuses on planning the response before drafting it.

---

## 5.2 Add or Activate a Dedicated Skill Specification

### File to change
- `backend/app/services/agent/agent_skill_registry.py`

### Add or formalise a skill
Suggested skill name:

```python
"reply-strategy"
```

Alternative naming:
```python
"response-planning"
```

### Suggested configuration
- `allowed_bundles`: likely `("thread_deep_read", "read_only_inbox")`
- `rollout_stage`: start as `"planned"`
- `auto_select`: `False` initially

### Suggested prompt intent
The skill should instruct the agent to:
- analyse what the sender wants
- recommend the best response goal
- recommend tone and level of detail
- identify key points to include
- avoid jumping straight to full draft unless user asks

### Example prompt direction
- “Use the reply-strategy workflow for this turn.”
- “Focus on tone, goal, must-include points, and recommended reply style.”
- “Return a compact founder-friendly strategy, then offer drafting as the next step.”

---

## 5.3 Extend Workflow Planning Logic

### File to change
- `backend/app/services/workflow/email_workflow_planner.py`

### Add reply-strategy markers
Suggested marker groups:

#### Direct strategy request markers
- `how should I respond`
- `how should I reply`
- `best way to reply`
- `reply strategy`
- `what tone`
- `what should I say`
- `before drafting`
- `how do I answer`

#### Tone/format markers
- `short reply`
- `formal`
- `professional`
- `polite`
- `brief`
- `detailed`
- `warm`
- `direct`

#### Action/goal markers
- `confirm`
- `decline`
- `clarify`
- `follow up`
- `send`
- `propose`
- `reply`
- `respond`

### Planning rule idea
A request should be considered a reply-strategy candidate when:
- the user explicitly asks for guidance on how to reply
- the thread clearly needs a response
- the user is asking for tone/approach/key points rather than a full draft

### Suggested planner result
Return something like:

```python
EmailWorkflowPlan(
    workflow_tag="needs_reply_strategy_brief",
    recommended_skill="reply-strategy",
    brief_type="reply_strategy_brief",
    precompute_priority=...,
    reasons=(...)
)
```

---

## 5.4 Add Reply Strategy Brief Generation

### Best architectural location
Use the same brief-generation pattern already used by the workflow service.

### File likely to change
- `backend/app/services/workflow/email_workflow_service.py`
- related helper/store code if needed

### Required behaviour
Given a thread context, generate a structured reply strategy brief containing:

- response goal
- recommended tone
- recommended detail level
- must-include points
- optional avoid/include warnings
- recommended next action
- optional “ready to draft” flag

### Suggested response goals
- `acknowledge_and_move_forward`
- `confirm`
- `clarify`
- `decline_politely`
- `delay_with_context`
- `propose_meeting`
- `send_materials`
- `request_more_information`
- `unknown`

### Suggested tone values
- `warm_professional`
- `concise_professional`
- `formal`
- `friendly`
- `direct`
- `cautious`
- `neutral`

### Suggested detail-level values
- `brief`
- `standard`
- `detailed`

### Suggested next-step values
- `generate_draft`
- `review_thread_first`
- `ask_clarifying_question`
- `no_reply_needed`
- `wait_before_reply`

---

## 5.5 Add a Dedicated Aggregation / Orchestration Layer

### New service recommendation
Create a dedicated backend service:

```text
backend/app/services/reply_strategy_service.py
```

### Why a separate service is recommended
Even if version 1 often handles one thread at a time, it is still useful to isolate:
- strategy inference
- tone recommendation
- key-point extraction
- output shaping

A dedicated service should:
1. read the current thread context
2. analyse sender intent and relationship
3. infer reply goal
4. recommend tone and reply shape
5. extract must-include points
6. return a compact strategy summary

### Core methods to implement
Suggested methods:
- `infer_reply_goal(...)`
- `infer_tone_strategy(...)`
- `extract_key_points(...)`
- `build_reply_strategy_brief(...)`

### Input sources
- thread context from `EmailWorkflowService`
- triage signals from `EmailTriageService`
- style profile from style-related layer
- contact metadata where useful

---

## 5.6 Add Tone and Strategy Heuristics

### Why this is needed
This feature becomes valuable only when it can answer:
- not just “reply needed”
but
- “how should I reply?”

### Suggested tone/strategy factors
- sender relationship (investor / client / recruiter / teammate)
- thread formality level
- urgency
- whether the sender asked a direct question
- whether the reply should keep momentum
- whether the user style profile prefers concise wording
- whether the thread is sensitive or corrective

### Example heuristic outcomes
- investor request for update → `warm_professional`, brief but proactive
- recruiter logistics question → `concise_professional`
- polite decline to low-value opportunity → `friendly` or `warm_professional`, brief
- unclear request from external contact → `clarify`, neutral/professional

### Important note
Use cautious recommendations.  
Avoid overconfident tone choices when thread evidence is weak.

---

## 5.7 Add a User-Facing Entry Point

### Where to wire it
Depending on your current request-routing flow, add intent recognition for:
- how should I reply
- reply strategy
- what tone should I use
- what should I include in my response

### Likely files to inspect/update
- request router / intent routing layer
- main email agent client integration layer
- any chat workflow feature entry already used for drafting

### Expected entry behaviour
When user intent is reply strategy:
1. route to reply strategy summary flow
2. call `ReplyStrategyService`
3. return compact strategy guidance
4. offer optional follow-ups:
   - generate draft
   - make it shorter
   - make it more formal
   - open thread

---

## 6. Detailed Implementation Plan

## Step 1: Stabilise planner support
### Files
- `backend/app/services/workflow/email_workflow_planner.py`

### Tasks
- add or formalise reply-strategy workflow tag
- add direct strategy-request markers
- distinguish strategy requests from full draft requests
- improve planner reasons for why a strategy workflow was selected

### Done when
A user request asking *how* to reply can be reliably classified into the correct workflow.

---

## Step 2: Add skill registry entry
### Files
- `backend/app/services/agent/agent_skill_registry.py`

### Tasks
- add or formalise `reply-strategy`
- define prompt lines
- define concise output expectations
- begin with planned rollout if needed

### Done when
Reply strategy becomes a first-class workflow option in the skill model.

---

## Step 3: Add brief generation
### Files
- `backend/app/services/workflow/email_workflow_service.py`
- related helper/store code if needed

### Tasks
- add support for `reply_strategy_brief`
- extract goal, tone, length recommendation, key points, next step
- use thread context and sender relationship
- keep output compact and actionable

### Done when
A single email thread can produce a structured reply strategy brief.

---

## Step 4: Build dedicated strategy service
### Files
- `backend/app/services/reply_strategy_service.py`

### Tasks
- analyse current thread
- infer response goal
- infer tone and detail level
- extract key points to include
- assemble final strategy payload

### Suggested ranking / inference factors
- sender importance
- reply_needed
- urgency
- relationship type
- current thread tone
- user style profile
- whether the sender asked for specific materials / confirmation / next step

### Done when
The backend can produce a reliable strategy-first response instead of always jumping to drafting.

---

## Step 5: Add API/service integration
### Files
- request routing layer
- main email agent client integration layer
- any draft-related feature entry layer

### Tasks
- recognise reply-strategy intent
- call `ReplyStrategyService`
- return concise strategy output
- add user-facing follow-up suggestions

### Done when
A natural-language question about how to respond triggers the correct workflow.

---

## Step 6: Add tests
### Files to add
- `backend/tests/test_reply_strategy_service.py`
- planner tests
- workflow service tests if needed

### Minimum test cases
1. detects explicit “how should I respond” request
2. recommends concise professional tone for recruiter logistics email
3. recommends warm professional tone for investor follow-up email
4. extracts key points for clarification-style reply
5. distinguishes strategy request from full-draft request
6. handles no-reply-needed case safely
7. returns cautious strategy when thread evidence is weak
8. supports “generate draft next” follow-up option

### Done when
Feature is stable enough to demo and refactor safely.

---

## 7. Suggested Data Contract

The final backend summary should return something like:

```json
{
  "summary_title": "Reply strategy",
  "thread_id": "thread_123",
  "reply_goal": "acknowledge_and_move_forward",
  "tone": "warm_professional",
  "detail_level": "brief",
  "key_points": [
    "Acknowledge the investor's request",
    "Provide a concise update",
    "Offer the next concrete step"
  ],
  "next_step": "generate_draft",
  "follow_up_options": [
    "generate draft",
    "make it shorter",
    "make it more formal",
    "open related thread"
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
This feature can use the same chat-based interaction model as current drafting and inbox workflows.

### Recommended response format
Return:
- one-line strategy summary
- tone
- length recommendation
- top 2–4 key points
- short follow-up options

### Good UX pattern
> “A good reply strategy here would be to respond briefly but proactively.  
> Use a warm professional tone, acknowledge the request, give one clear answer, and propose the next step.  
> Would you like me to turn that into a polished draft?”

This is better than forcing the user into a full draft immediately.

---

## 9. Suggested Development Order

### Phase 1
- planner support hardening
- skill spec
- strategy-request detection

### Phase 2
- reply strategy brief generation
- tone/detail heuristics
- dedicated service layer

### Phase 3
- request routing
- frontend integration
- test hardening

### Phase 4
Optional improvements:
- better style-profile conditioning
- stronger boundary/decline recommendations
- multi-variant strategy suggestions
- domain-specific strategies for investor / hiring / client emails

---

## 10. Risks and Mitigations

### Risk 1: Overlap with direct drafting
This feature may feel redundant if the system already drafts replies.

**Mitigation**
- keep this feature clearly strategy-first
- return tone + goal + key points first, then offer draft generation

### Risk 2: Weak tone inference
The system may recommend an inappropriate tone if context is thin.

**Mitigation**
- use cautious defaults like `concise_professional`
- rely on thread context and user style profile where possible

### Risk 3: Strategy output too vague
A generic answer like “be polite and professional” is not useful enough.

**Mitigation**
- require explicit fields:
  - goal
  - tone
  - detail level
  - key points
  - next step

### Risk 4: Confusion between no-reply-needed and strategy-needed
Some threads may not require a response at all.

**Mitigation**
- include a possible `no_reply_needed` next-step/status path
- use triage and thread-state signals before assuming reply is required

---

## 11. Definition of Done

This feature can be considered complete for version 1 when:

- a reply-strategy request is correctly routed
- the system distinguishes strategy requests from direct draft requests
- strategy outputs contain meaningful goal/tone/key-point guidance
- tone recommendations are reasonably aligned with thread context
- the system can safely indicate when no reply is needed
- each output includes:
  - reply goal
  - tone
  - detail level
  - key points
  - next step
- automated tests cover the main cases
- the output is concise enough for founder-style inbox use

---

## 12. Recommended File Change List

### New file
- `backend/app/services/reply_strategy_service.py`

### Existing files likely to change
- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/workflow/email_workflow_planner.py`
- `backend/app/services/workflow/email_workflow_service.py`
- style-related integration layer if needed
- request routing / feature integration files
- backend tests for planner and workflow integration

---

## 13. Short Developer Summary

To build **Draft Reply Strategy Query** properly on top of the current codebase:

1. add or formalise a reply-strategy workflow tag
2. add or activate a `reply-strategy` skill
3. teach the planner how to recognise strategy requests separately from full draft requests
4. generate structured reply strategy briefs from thread context
5. infer tone, goal, and key points using cautious heuristics
6. expose it through the standard request flow
7. keep draft generation as the next optional step
8. test it with investor, recruiter, logistics, clarification, and no-reply-needed cases

This approach fits the current architecture and turns existing drafting capability into a more controllable strategy-first workflow.
