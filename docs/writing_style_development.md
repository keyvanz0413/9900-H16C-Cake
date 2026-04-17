# Writing Style Development Design

## 1. Purpose

This document describes the intended design for the Writing Style feature in the
current `9900-H16C-Cake` project.

The project architecture is:

```text
oo-chat frontend
  -> Next.js API route
  -> hosted email-agent backend
  -> Gmail / Calendar / Memory tools
  -> final agent response
  -> oo-chat display
```

`oo-chat` should remain a general chat transport and display layer. Writing
style logic should live in `email-agent` as tools, local persisted profile data,
and prompt workflow.

The goal is:

> Given a user request such as "Write this in my usual style" or "Draft a reply
> that sounds like me", the agent should inspect the current email context,
> learn the user's writing patterns from sent emails or stored style memory,
> then return a polished draft that matches the user's normal tone and structure.

## 2. Design Constraints

Writing style support has two separate parts:

- understanding the user's style
- generating a draft using that style

The first part should be handled by structured tool output as much as possible.
The second part can be handled by the LLM using the current email thread and the
structured style profile.

Important boundary:

> Writing Style should produce drafts only. It should not send an email unless a
> separate send workflow exists and the user explicitly confirms the final send.

The agent should not:

- silently send emails
- claim that a reply has been sent when only a draft was produced
- copy unrelated sensitive details from previous sent emails
- force a casual style when the recipient or context requires a more formal tone
- invent a stable writing style from too few examples without saying confidence
  is low

## 3. Desired Design Direction

Writing Style should be built around a reusable style profile tool.

Recommended flow:

```text
User asks for a reply in their style
  -> agent retrieves the current email or thread context
  -> agent calls get_writing_style_profile
  -> tool checks whether a saved style profile exists in data/
  -> if no profile exists, agent asks whether to learn the user's style first
  -> if profile is older than 7 days, agent warns and asks whether to refresh
  -> tool returns saved or refreshed structured style profile
  -> agent drafts the reply using the thread context and style profile
  -> agent shows the draft to the user for review
```

The design principle is:

> The tool should summarize stable writing habits. The LLM should apply those
> habits to the specific draft.

This keeps the style behavior consistent while still allowing the agent to adapt
to different situations.

## 4. Proposed Tool

### Tool Name

```python
get_writing_style_profile
```

### Proposed Signature

```python
def get_writing_style_profile(
    sample_count: int = 20,
    recipient_query: str = "",
    purpose: str = "",
    use_saved_profile: bool = True,
    refresh_profile: bool = False,
    stale_after_days: int = 7,
) -> str:
    """Analyze sent emails and return the user's structured writing style."""
```

### Tool Type

Read-only by default.

The normal draft path should read a saved profile from `data/` when one exists.
If profile learning or refreshing is requested, the tool may write the extracted
style profile to `data/`, but it should not store raw email bodies.

The tool should not:

- send emails
- create drafts in the email provider
- mark emails as read
- expose full historical sent-email content to the final answer
- store private email bodies in local files or memory

### Responsibilities

The tool should:

1. Load an existing writing style profile from `data/writing_style_profile.json`
   if available.
2. Check whether the saved profile is missing, valid, fresh, or stale.
3. Search recent sent emails for style examples when learning or refreshing is
   requested.
3. Prefer recipient-specific examples when `recipient_query` is provided.
4. Analyze greetings, sign-offs, tone, length, structure, and phrasing patterns.
5. Detect whether the style changes by audience or purpose.
6. Return a structured profile with freshness, confidence, and limitations.
7. Avoid returning long quoted examples from private emails.
8. Save or refresh the stored profile if `refresh_profile=True`.

## 5. Persistent Profile Design

Writing style should be saved locally so the user does not need to relearn it
every time they open the app.

Recommended file:

```text
email-agent/data/writing_style_profile.json
```

Recommended behavior:

1. First draft request:
   - If no saved profile exists, the agent should not silently analyze sent
     emails.
   - The agent should ask:

```text
I do not have a saved writing style profile yet. Would you like me to learn your
style from recent sent emails before drafting?
```

2. User says yes:
   - The agent calls `get_writing_style_profile(refresh_profile=True)`.
   - The tool analyzes sent emails.
   - The tool saves the structured profile to `data/writing_style_profile.json`.
   - The agent drafts using the new profile.

3. User says no:
   - The agent drafts using only the current instruction and thread context.
   - The response should say it was not based on a saved writing style profile.

4. Later draft request:
   - If the saved profile exists and is fresh, the agent reads it directly.
   - The agent does not need to ask the user every time.

5. Stale profile:
   - If `last_updated` is more than 7 days old, the agent should warn the user
     before drafting.
   - The agent should ask whether to refresh:

```text
Your saved writing style profile has not been updated for more than 7 days.
Would you like me to relearn it from recent sent emails before I draft this?
```

6. User says refresh:
   - The tool refreshes the profile and updates `last_updated`.

7. User skips refresh:
   - The agent can draft using the old profile.
   - The response should mention that the draft used the existing saved profile.

This design gives the user control while avoiding repeated analysis for every
draft.

## 6. Proposed Saved File Schema

The saved profile should be JSON.

Example:

```json
{
  "version": 1,
  "created_at": "2026-04-18",
  "last_updated": "2026-04-18",
  "stale_after_days": 7,
  "source": {
    "sample_count_used": 20,
    "scope": "sent_emails",
    "recipient_specific_profiles": []
  },
  "profile": {
    "tone": "polite, concise, mildly proactive",
    "formality": "medium",
    "directness": "high",
    "warmth": "medium",
    "greeting_patterns": [
      "Hi {name}",
      "Hey {name}"
    ],
    "sign_off_patterns": [
      "Best",
      "Thanks"
    ],
    "sentence_style": {
      "average_length": "short",
      "uses_contractions": true,
      "uses_bullets": "sometimes",
      "uses_exclamation_marks": "rarely"
    },
    "structure": [
      "short acknowledgement",
      "direct answer",
      "clear next step"
    ],
    "common_phrasing": [
      "sounds good",
      "happy to",
      "let me know"
    ],
    "avoid": [
      "overly formal wording",
      "long explanations",
      "unnecessary apologies"
    ]
  },
  "confidence": "medium",
  "limitations": [
    "Recipient-specific style was not available."
  ]
}
```

## 7. Proposed Tool Output Schema

The tool should return JSON as a string.

Example:

```json
{
  "intent": "writing_style_profile",
  "source": {
    "sample_count_requested": 20,
    "sample_count_used": 12,
    "scope": "sent_emails",
    "recipient_specific": false,
    "saved_profile_used": true,
    "profile_path": "data/writing_style_profile.json",
    "profile_created_at": "2026-04-18",
    "profile_last_updated": "2026-04-18",
    "profile_age_days": 0,
    "is_stale": false,
    "stale_after_days": 7
  },
  "profile": {
    "tone": "polite, concise, mildly proactive",
    "formality": "medium",
    "directness": "high",
    "warmth": "medium",
    "greeting_patterns": [
      "Hi {name}",
      "Hey {name}"
    ],
    "sign_off_patterns": [
      "Best",
      "Thanks"
    ],
    "sentence_style": {
      "average_length": "short",
      "uses_contractions": true,
      "uses_bullets": "sometimes",
      "uses_exclamation_marks": "rarely"
    },
    "structure": [
      "short acknowledgement",
      "direct answer",
      "clear next step"
    ],
    "common_phrasing": [
      "sounds good",
      "happy to",
      "let me know"
    ],
    "avoid": [
      "overly formal wording",
      "long explanations",
      "unnecessary apologies"
    ]
  },
  "audience_adjustment": {
    "recipient_query": "",
    "recommendation": "Use the general style profile unless the thread is formal."
  },
  "profile_state": "fresh",
  "requires_user_confirmation": false,
  "recommended_agent_action": "Draft using the saved style profile.",
  "confidence": "medium",
  "limitations": [
    "Only 12 usable sent emails were available.",
    "Recipient-specific style was not available."
  ]
}
```

Recommended `profile_state` values:

```text
missing
fresh
stale
refreshed
unavailable
```

Recommended `requires_user_confirmation` behavior:

- `missing`: true
- `stale`: true
- `fresh`: false
- `refreshed`: false
- `unavailable`: true

## 8. Style Analysis Logic

The first version can use simple rule-based extraction before the LLM applies
the profile.

Recommended signals:

| Style Area | Signals |
| --- | --- |
| Greeting | `Hi`, `Hey`, `Dear`, no greeting |
| Sign-off | `Best`, `Thanks`, `Cheers`, name-only, no sign-off |
| Formality | formal phrases, casual phrases, contractions |
| Length | average sentence count, paragraph count, word count |
| Structure | acknowledgement, answer, explanation, next step |
| Warmth | appreciation, friendly openers, softeners |
| Directness | clear asks, concise decisions, explicit next steps |
| Formatting | bullets, numbered lists, short paragraphs |
| Punctuation | exclamation marks, question marks, emojis |

The tool does not need to perfectly imitate the user. It should produce a stable
style profile that the agent can use consistently.

## 9. Drafting Workflow

When the user asks for a style-matched draft, the agent should follow this
workflow:

1. Identify the email or thread being replied to.
2. Read enough thread context to understand the sender's request.
3. Call `get_writing_style_profile(use_saved_profile=True)`.
4. If the profile is missing, ask whether to learn the style before drafting.
5. If the profile is stale, ask whether to refresh it before drafting.
6. If the user agrees, call `get_writing_style_profile(refresh_profile=True)`.
7. Decide the reply goal:
   - answer
   - confirm
   - decline
   - delay
   - clarify
   - propose a next step
8. Draft the reply using the fresh or accepted existing style profile.
9. Show the draft to the user.
10. Clearly state that the email has not been sent.

Recommended response shape:

```text
Here is a draft in your usual style:

Subject: ...

Hi ...

...

This is only a draft. I have not sent it.
```

## 10. Optional Draft Helper

A second helper can be added later if draft output needs to become more
standardized.

### Tool Name

```python
draft_reply_with_style
```

### Proposed Signature

```python
def draft_reply_with_style(
    thread_context: str,
    reply_goal: str,
    style_profile_json: str = "",
    recipient_query: str = "",
) -> str:
    """Return a structured email draft using the user's writing style."""
```

This helper should only return draft text. It should not send the email.

In the first implementation, this helper is optional because the agent can draft
directly from:

- current thread context
- `get_writing_style_profile` output
- prompt instructions

## 11. Data Storage Design

The primary storage should be a local JSON file under `email-agent/data/`.
This is suitable because the style profile is a compact user preference that
should survive app restarts and later login sessions.

Recommended file paths:

```text
email-agent/data/writing_style_profile.json
email-agent/data/writing_style_profiles/
```

`writing_style_profile.json` should store the general profile. The optional
`writing_style_profiles/` folder can store recipient-specific profiles later.

Recommended saved content:

- summarized style profile
- confidence level
- sample count
- created date
- last updated date
- stale threshold, default 7 days
- audience-specific notes

The saved profile should not store:

- raw sent emails
- private thread content
- full quoted examples
- sensitive contact details that are not needed for style

Memory can still be used as a secondary source for short preferences, but the
canonical writing style profile should be the local data file.

If the saved profile and recent sent emails disagree during refresh, recent sent
emails should usually win. The final response can mention that the profile was
refreshed if relevant.

## 12. Prompt Guidance

The Gmail and Outlook prompts should eventually include a specific Writing Style
workflow.

Recommended prompt instruction:

```text
When the user asks to write or draft in their usual style:
1. Read the current email/thread context.
2. Call get_writing_style_profile with recipient_query when a recipient is known.
3. If no saved profile exists, ask whether to learn from recent sent emails.
4. If the saved profile is older than 7 days, ask whether to refresh it.
5. Use the returned or user-approved style profile to draft the reply.
6. Keep the reply appropriate to the recipient and situation.
7. Show the draft to the user.
8. Do not send unless the user explicitly confirms sending.
```

The prompt should also tell the agent not to expose detailed private examples
from old sent emails. The final answer should describe style briefly, then show
the draft.

## 13. Example User Flows

### First Use

User:

```text
Draft a reply that sounds like me.
```

Agent response before learning:

```text
I do not have a saved writing style profile yet. Would you like me to learn your
style from recent sent emails before drafting?
```

User:

```text
yes
```

Agent internal workflow:

```text
search_emails / get_email_thread
get_writing_style_profile(
  sample_count=20,
  recipient_query="sender@example.com",
  refresh_profile=True
)
generate draft from thread context + style profile
```

Agent response:

```text
Here is a draft in your usual style:

Subject: Re: Project update

Hi Sarah,

Thanks for the update. This sounds good to me.

I can review the latest version tomorrow and send comments by the afternoon.
Let me know if there is anything specific you want me to focus on.

Best,
Aiden

I have not sent this yet.
```

### Saved Profile Is Fresh

User:

```text
Draft a reply that sounds like me.
```

Agent internal workflow:

```text
search_emails / get_email_thread
get_writing_style_profile(use_saved_profile=True)
generate draft from saved style profile
```

Agent response should not ask to relearn the profile.

### Saved Profile Is Stale

User:

```text
Draft a reply that sounds like me.
```

Agent response before drafting:

```text
Your saved writing style profile has not been updated for more than 7 days.
Would you like me to relearn it from recent sent emails before I draft this?
```

If the user says no, the agent may continue with the old profile and mention that
the draft uses the existing saved profile.

## 14. Edge Cases

### Too Few Sent Emails

If there are too few examples, the tool should return `confidence: "low"` and
the agent should say the draft is based on limited evidence.

### Recipient-Specific Style Missing

If no examples exist for a specific recipient, use the general style profile and
adapt based on the current thread's tone.

### Formal Context

If the user's usual style is casual but the email is formal, the agent should
preserve the user's concise habits while making the draft appropriately formal.

### Sensitive Prior Emails

The tool should summarize style patterns without exposing private details from
unrelated emails.

### User Provides Style Instructions

If the user gives direct instructions such as "make it more formal" or "shorter",
those instructions should override the stored profile for that draft.

### Missing Data Directory

If `email-agent/data/` does not exist, the tool should create it when saving a
profile. If saving fails, the tool should still return a profile for the current
draft and explain that persistence failed.

### Corrupted Saved Profile

If `data/writing_style_profile.json` exists but is invalid JSON or has missing
required fields, the tool should treat it as unavailable and ask the user whether
to relearn the style.

## 15. Testing Plan

Recommended tests:

1. Profile extraction returns valid JSON.
2. Sent-email samples produce expected greeting and sign-off patterns.
3. Too few samples return low confidence.
4. Recipient-specific query prefers matching sent emails.
5. Raw email body content is not returned in the style profile.
6. Saved profile is read from `data/writing_style_profile.json`.
7. Missing saved profile returns `profile_state: "missing"` and requires user
   confirmation before learning.
8. Stale saved profile returns `profile_state: "stale"` after 7 days.
9. `refresh_profile=False` does not write to `data/`.
10. `refresh_profile=True` writes only summarized style data, not raw emails.
11. Corrupted saved profile is handled safely.
12. Draft workflow response states that the email has not been sent.

## 16. Implementation Checklist

Recommended implementation order:

1. Create `email-agent/tools/writing_style.py`.
2. Add `configure_writing_style(email_tool, memory_tool)`.
3. Add `get_writing_style_profile`.
4. Add local profile helpers for:
   - reading `data/writing_style_profile.json`
   - checking `last_updated`
   - detecting stale profiles after 7 days
   - saving refreshed profiles
5. Export the tool from `email-agent/tools/__init__.py`.
6. Register the tool in `email-agent/agent.py`.
7. Add Writing Style workflow instructions to Gmail and Outlook prompts.
8. Add focused tests in `email-agent/tests/test_writing_style_tool.py`.
9. Rebuild Docker before testing through `oo-chat`.

## 17. Success Criteria

Writing Style is successful when:

- the agent consistently calls the style tool for style-matched drafting
- the style profile is saved under `email-agent/data/`
- later sessions can reuse the saved style profile
- first use asks the user whether to learn their style
- stale profiles older than 7 days trigger a refresh question
- the returned profile has predictable structure
- drafts match the user's usual tone without copying old email content
- drafts remain appropriate for the recipient and context
- the agent clearly separates draft creation from sending
- tests cover profile extraction, low-confidence cases, and privacy boundaries
