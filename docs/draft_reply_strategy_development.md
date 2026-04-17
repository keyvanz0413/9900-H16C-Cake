# Draft Reply Strategy Development Design

## 1. Purpose

This document describes the intended design for the Draft Reply Strategy feature
in the current `9900-H16C-Cake` project.

The project architecture is:

```text
oo-chat frontend
  -> Next.js API route
  -> hosted email-agent backend
  -> Gmail / Calendar / Memory tools
  -> final agent response
  -> oo-chat display
```

`oo-chat` should remain a transport and display layer. Draft reply reasoning
should live in `email-agent` as tools and prompt workflow.

The goal is:

> Given a user request such as "How should I respond to this email?" or "Draft a
> reply to him", the agent should inspect the relevant thread, identify the
> sender's request, choose a reply strategy, check the user's writing style
> profile, and then either return a draft or ask for the required confirmation
> before drafting.

This pair is different from Writing Style:

- Writing Style answers: "How does the user usually write?"
- Draft Reply Strategy answers: "What should this specific reply say?"

Draft Reply Strategy may use Writing Style, but it should not be replaced by
Writing Style.

## 2. Design Constraints

Drafting has three separate responsibilities:

1. Understand the email/thread context.
2. Decide the reply strategy.
3. Produce draft text using the user's style when available.

Important boundary:

> Draft Reply Strategy should create draft text only. It should not send, reply,
> archive, label, or mark emails unless a separate explicit write workflow is
> triggered.

The agent should not:

- send the draft in the same turn as a draft-only request
- claim that it tried to send a draft
- invent missing thread details
- ignore an expired or missing writing style profile
- block all drafting forever if the user declines style learning
- copy private examples from previous sent emails

## 3. Desired Design Direction

Draft Reply Strategy should be built around a read-only strategy tool.

Recommended flow:

```text
User asks for a reply or draft
  -> agent calls get_draft_reply_strategy
  -> tool gathers thread context, contact context, and writing style profile state
  -> tool returns structured strategy and draft readiness
  -> if style profile is missing/stale, agent asks the user what to do
  -> if ready, agent writes the draft from the structured strategy
  -> agent shows the draft and states that it has not been sent
```

The design principle is:

> The Draft Reply tool should decide what the reply needs to accomplish. The LLM
> should turn that structured strategy into natural email text.

This avoids hardcoding draft text in Python while still making the workflow more
stable than relying on free-form prompt behavior.

## 4. Proposed Tool

### Tool Name

```python
get_draft_reply_strategy
```

### Proposed Signature

```python
def get_draft_reply_strategy(
    user_request: str,
    contact_query: str = "",
    thread_query: str = "",
    email_id: str = "",
    reply_goal: str = "",
    include_writing_style: bool = True,
    allow_stale_style: bool = False,
    max_emails: int = 10,
) -> str:
    """Collect context and return a structured reply strategy."""
```

### Tool Type

Read-only.

The tool should not:

- send emails
- call provider `reply`
- call provider `send`
- create a draft in Gmail/Outlook
- archive, label, star, or mark emails
- write or refresh the style profile unless the user explicitly requested style
  learning through the Writing Style tool

### Responsibilities

The tool should:

1. Resolve the target email or thread.
2. Read the relevant email body when `email_id` is available.
3. Search related emails when only a contact or thread query is available.
4. Identify the sender, recipient, subject, and latest message.
5. Summarize what the sender is asking for.
6. Infer the reply goal:
   - confirm
   - decline
   - clarify
   - delay
   - provide information
   - propose next step
   - acknowledge only
7. Check contact memory when available.
8. Check writing style profile state through `get_writing_style_profile`.
9. Return whether the agent is ready to draft.
10. Return the key points the draft should include.
11. Return safety notes that no email has been sent.

## 5. Relationship With Writing Style

Draft Reply Strategy should depend on Writing Style but not duplicate it.

Recommended dependency:

```text
get_draft_reply_strategy
  -> calls/uses get_writing_style_profile(use_saved_profile=True)
  -> includes style_profile_state in the output
```

If the style profile is missing:

```json
{
  "draft_readiness": {
    "ready_to_draft": false,
    "blocked_by": "missing_writing_style",
    "user_question": "I do not have a saved writing style profile yet. Would you like me to learn your style from recent sent emails before drafting?"
  }
}
```

If the style profile is stale:

```json
{
  "draft_readiness": {
    "ready_to_draft": false,
    "blocked_by": "stale_writing_style",
    "user_question": "Your saved writing style profile has not been updated for more than 7 days. Would you like me to refresh it before drafting?"
  }
}
```

If the user declines style learning or refresh, the next call can set:

```python
allow_stale_style=True
```

or the agent can draft without a style profile and clearly say:

```text
I drafted this without a saved writing style profile.
```

## 6. Proposed Output Schema

The tool should return JSON as a string.

Example:

```json
{
  "intent": "draft_reply_strategy",
  "source": {
    "user_request": "draft a reply to him, let him know I will join the meeting on time",
    "contact_query": "Aiden_Yang",
    "thread_query": "confirm a meeting",
    "email_id": "19d6db41597d2640",
    "related_emails_found": 1
  },
  "thread_context": {
    "sender": "Aiden_Yang <945430408@qq.com>",
    "subject": "confirm a meeting",
    "latest_message_summary": "The sender reminded the user about a meeting this Sunday at 6:00 pm.",
    "detected_request": "Confirm attendance for the meeting.",
    "important_details": [
      "meeting is this Sunday",
      "meeting time is 6:00 pm"
    ],
    "raw_email_included": false
  },
  "reply_strategy": {
    "goal": "confirm",
    "tone": "polite and concise",
    "relationship_context": "known contact from email thread",
    "key_points": [
      "thank them for the reminder",
      "confirm that the user will join on time",
      "repeat the meeting time for clarity"
    ],
    "avoid": [
      "claiming the email has been sent",
      "adding unavailable details",
      "over-explaining"
    ]
  },
  "writing_style": {
    "included": true,
    "profile_state": "fresh",
    "confidence": "medium",
    "profile": {
      "tone": "polite, concise, and collaborative",
      "greeting_patterns": ["Hi {name}"],
      "sign_off_patterns": ["Best"]
    }
  },
  "draft_readiness": {
    "ready_to_draft": true,
    "blocked_by": "",
    "user_question": "",
    "needs_user_confirmation_before_send": true
  },
  "recommended_agent_action": "Write a draft using the reply strategy and writing style profile.",
  "safety_notes": [
    "No email has been sent.",
    "No provider draft has been created.",
    "Do not call send or reply unless the user explicitly confirms sending."
  ]
}
```

## 7. Draft Readiness States

Recommended readiness labels:

```text
ready
missing_thread_context
missing_writing_style
stale_writing_style
needs_user_clarification
unsafe_to_draft
```

Suggested behavior:

| State | Meaning | Agent behavior |
| --- | --- | --- |
| `ready` | Enough context and style are available | Produce draft text |
| `missing_thread_context` | The target email/thread is unclear | Ask which email/thread |
| `missing_writing_style` | No saved style profile exists | Ask whether to learn style |
| `stale_writing_style` | Saved style is older than threshold | Ask whether to refresh |
| `needs_user_clarification` | The desired reply content is ambiguous | Ask one focused question |
| `unsafe_to_draft` | Request would be misleading or risky | Explain limitation |

## 8. Draft Generation Boundary

There are two reasonable implementation levels.

### Level 1: Strategy Tool Only

The tool returns structured strategy. The LLM writes the final draft from that
strategy.

This is recommended for the first implementation because it fits the current
agent architecture and avoids building a second generation layer inside tools.

### Level 2: Strategy + Draft Tool

A second tool can later be added:

```python
def render_draft_reply(strategy_json: str) -> str:
    """Render a draft from a structured reply strategy."""
```

This would make draft formatting more consistent, but it should still not send
the email.

For now, prefer Level 1.

## 9. Prompt Guidance

The Gmail and Outlook prompts should eventually be updated so that normal draft
requests use Draft Reply Strategy as the entry point.

Recommended prompt instruction:

```text
When the user asks to draft, write, prepare, or plan a reply:
1. Call get_draft_reply_strategy.
2. If draft_readiness.ready_to_draft is false, follow user_question or recommended_agent_action.
3. If ready_to_draft is true, write the draft using reply_strategy and writing_style.
4. State clearly that the draft has not been sent.
5. Do not call send/reply unless the user separately confirms sending.
```

This should replace the current behavior where the model directly drafts from
email context.

## 10. Example User Flow

User:

```text
draft a reply to him, let him know I will join the meeting on time
```

Agent internal workflow:

```text
get_draft_reply_strategy(
  user_request="draft a reply to him, let him know I will join the meeting on time",
  contact_query="Aiden_Yang",
  thread_query="confirm a meeting"
)
```

If writing style is missing, agent response:

```text
I do not have a saved writing style profile yet. Would you like me to learn your
style from recent sent emails before drafting?
```

If ready, agent response:

```text
Here is a draft:

Subject: Re: confirm a meeting

Hi Aiden,

Thanks for the reminder. I will join the meeting on time this Sunday at 6:00 pm.

Best,
Kty

I have not sent this.
```

## 11. Edge Cases

### Pronoun Reference

If the user says "him" or "her", the tool should use recent conversation context
when available. If the target is still unclear, return `missing_thread_context`.

### Multiple Candidate Threads

If several emails match the contact or topic, the tool should return candidates
and ask the user to choose.

### Missing Style Profile

The tool should not learn style by itself. It should return a blocking
readiness state and let the agent ask for confirmation.

### User Declines Style Learning

The agent may call the strategy tool again with style disabled or draft without
a saved style profile, but it should say that no saved style profile was used.

### Send Request

If the user asks to send, the draft should still be prepared first. Sending must
remain a separate confirmed action.

## 12. Testing Plan

Recommended tests:

1. Strategy tool returns valid JSON.
2. Email ID path reads the exact email body.
3. Contact/thread query path searches related emails.
4. Meeting reminder email produces `goal: "confirm"`.
5. Ambiguous target returns `missing_thread_context`.
6. Missing writing style returns `missing_writing_style`.
7. Stale writing style returns `stale_writing_style`.
8. Fresh writing style returns `ready`.
9. Tool output includes no raw old sent-email bodies.
10. Tool never calls provider `send` or `reply`.

## 13. Implementation Checklist

Recommended implementation order:

1. Create `email-agent/tools/draft_reply.py`.
2. Add `configure_draft_reply(email_tool, memory_tool)`.
3. Add `get_draft_reply_strategy`.
4. Reuse `get_writing_style_profile` to include style state.
5. Export the tool from `email-agent/tools/__init__.py`.
6. Register the tool in `email-agent/agent.py`.
7. Update Gmail and Outlook prompts so draft requests call this tool first.
8. Add focused tests in `email-agent/tests/test_draft_reply_tool.py`.
9. Rebuild Docker before testing through `oo-chat`.

## 14. Success Criteria

Draft Reply Strategy is successful when:

- normal draft requests call the draft strategy tool first
- the tool returns stable reply goals and key points
- missing or stale writing style blocks drafting until the user chooses what to do
- generated drafts use the strategy instead of free-form guessing
- draft-only requests never send or claim to send
- tests cover ready, missing-style, stale-style, and ambiguous-thread cases
