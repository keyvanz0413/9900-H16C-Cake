# Meeting Schedule Development Design

## 1. Purpose

This document describes the intended design for the Meeting Schedule feature in
the current `9900-H16C-Cake` project.

The project architecture is:

```text
oo-chat frontend
  -> Next.js API route
  -> hosted email-agent backend
  -> Gmail / Calendar / Memory tools
  -> final agent response
  -> oo-chat display
```

`oo-chat` should remain a general chat transport and display layer. Meeting
scheduling logic should live in `email-agent` as tools and prompt workflow.

The goal is:

> Given a user request such as "Help me schedule this meeting", "Reply with
> times I am available", or "Check when my recent meeting with the investor is",
> the agent should gather email-thread context, calendar availability, contact
> context, and meeting status, then return a clear recommendation or scheduling
> draft.

## 2. Design Constraints

Meeting scheduling has both read-only and write-action parts.

Read-only actions include:

- detecting meeting intent
- finding related email threads
- reading relevant email bodies
- checking contact memory
- checking calendar availability
- identifying proposed or confirmed times
- drafting a scheduling reply

Write actions include:

- sending a scheduling email
- creating a calendar event
- creating a Google Meet link
- updating or cancelling a calendar event

The first implementation should focus on read-only scheduling assistance. Write
actions should only happen after explicit user confirmation and only be reported
as successful when the provider tool returns a successful result.

Important boundary:

> The agent must not say a meeting is booked unless a calendar write tool
> actually succeeded or a matching calendar event is found.

If only an email thread contains acceptance language, the agent should say:

```text
This appears confirmed in the email thread, but I did not find a matching
calendar event.
```

## 3. Desired Design Direction

Meeting Schedule should be built around a structured context tool.

Recommended flow:

```text
User asks for meeting scheduling help
  -> agent calls get_meeting_schedule_context
  -> tool gathers email, contact, and calendar facts
  -> tool returns structured meeting context
  -> agent recommends slots or drafts a reply
  -> user confirms any write action separately
```

The design principle is:

> The context tool should collect reliable scheduling facts. The LLM should use
> those facts to explain, recommend, and draft.

## 4. Proposed Tool

### Tool Name

```python
get_meeting_schedule_context
```

### Proposed Signature

```python
def get_meeting_schedule_context(
    contact_query: str = "",
    thread_query: str = "",
    requested_date: str = "",
    requested_time: str = "",
    duration_minutes: int = 30,
    days_ahead: int = 7,
    max_emails: int = 10,
) -> str:
    """Collect structured context for scheduling a meeting."""
```

### Tool Type

Read-only.

The tool should not:

- send emails
- create calendar events
- create Google Meet links
- modify existing calendar events
- mark emails as read
- archive emails

### Responsibilities

The tool should:

1. Resolve the requested contact or thread query.
2. Search recent emails related to the contact, subject, or meeting language.
3. Identify meeting-related messages and proposed times.
4. Detect whether the thread appears proposed, email-confirmed, calendar-confirmed,
   or unclear.
5. Check contact memory if available.
6. Check calendar availability for the requested date or upcoming days.
7. Identify conflicts with existing events.
8. Suggest suitable time slots.
9. Return structured context for the agent to explain or draft from.

## 5. Proposed Output Schema

The tool should return JSON as a string.

Example:

```json
{
  "intent": "meeting_schedule",
  "contact": {
    "query": "Wenyu Ding",
    "email": "wenyu.ding1@student.unsw.edu.au",
    "name": "Wenyu Ding",
    "source": "email_search"
  },
  "request": {
    "requested_date": "2026-04-20",
    "requested_time": "15:00",
    "duration_minutes": 30
  },
  "thread_context": {
    "related_emails_found": 3,
    "latest_subject": "Reminder: Meeting Tomorrow at 4:00 PM",
    "summary": "Recent messages discuss meeting reminders and availability.",
    "proposed_times": [
      {
        "date": "2026-04-20",
        "time": "15:00",
        "source": "user_request"
      }
    ]
  },
  "calendar": {
    "availability_checked": true,
    "available_slots": [
      {
        "start": "2026-04-20 15:00",
        "end": "2026-04-20 15:30"
      }
    ],
    "conflicts": [],
    "matching_event_found": false
  },
  "agreement": {
    "participant_found": true,
    "exact_date_found": true,
    "exact_time_found": true,
    "meeting_intent_found": true,
    "acceptance_found": true,
    "later_cancellation_or_reschedule_found": false,
    "ready_to_create_calendar_event": true,
    "confidence": "high"
  },
  "status": "draft_needed",
  "calendar_action": "ready_to_create",
  "missing_requirements": [],
  "evidence": [
    {
      "type": "proposal",
      "text": "Would you be available to meet on 20 Apr at 15:00?"
    },
    {
      "type": "acceptance",
      "text": "Yes, 20 Apr at 15:00 works for me."
    }
  ],
  "recommended_action": "Draft a scheduling reply offering 20 Apr at 15:00.",
  "safety_notes": [
    "No email has been sent.",
    "No calendar event has been created."
  ]
}
```

## 6. Meeting Agreement Criteria

The tool must distinguish an agreed email-thread meeting from a calendar-booked
meeting.

A meeting is ready to be added to calendar only when all of these requirements
are true:

1. `participant_found`: the other participant can be resolved to a specific
   person or email address.
2. `exact_date_found`: the meeting date is specific, such as `2026-04-20`,
   `20 Apr`, or a resolvable relative date such as `next Monday`.
3. `exact_time_found`: the meeting time is specific, such as `15:00`, `3 PM`,
   or `2-3 PM`.
4. `meeting_intent_found`: the thread is clearly about a meeting, call, chat,
   interview, appointment, sync, catch-up, or similar event.
5. `acceptance_found`: one participant clearly accepts the proposed time.
6. `later_cancellation_or_reschedule_found` is false: no later message cancels,
   postpones, or asks to move the meeting.

If all requirements are true:

```json
{
  "status": "email_confirmed",
  "calendar_action": "ready_to_create",
  "agreement": {
    "ready_to_create_calendar_event": true,
    "confidence": "high"
  }
}
```

The agent may then ask the user whether to create the calendar event. It must
not say the meeting is booked yet.

If a matching calendar event already exists:

```json
{
  "status": "calendar_confirmed",
  "calendar_action": "already_exists"
}
```

If the calendar creation tool later succeeds:

```json
{
  "status": "write_action_succeeded",
  "calendar_action": "created"
}
```

### Acceptance Signals

Strong acceptance language includes:

```text
yes
works for me
that works
confirmed
see you then
let's do [time]
I can do [time]
that time is fine
sounds good
looking forward to meeting then
```

Chinese acceptance language can include:

```text
可以
没问题
确认
就这个时间
到时候见
周一三点可以
```

Acceptance is not enough by itself. The thread still needs a specific
participant, date, time, and meeting intent.

### Cancellation Or Reschedule Signals

Later messages should override earlier confirmations when they include language
such as:

```text
can we reschedule
need to cancel
that no longer works
can we move it
can't make it
let's postpone
```

Chinese cancellation or reschedule language can include:

```text
改时间
取消
推迟
换个时间
我来不了
重新约
```

If such a later message exists, use:

```json
{
  "status": "reschedule_requested",
  "calendar_action": "do_not_create_yet",
  "agreement": {
    "ready_to_create_calendar_event": false
  }
}
```

### Missing Requirements

When the meeting is not ready for calendar creation, the tool should explain why
with `missing_requirements`.

Examples:

```json
{
  "status": "proposed",
  "calendar_action": "do_not_create_yet",
  "missing_requirements": ["exact_time", "acceptance"]
}
```

```json
{
  "status": "needs_more_context",
  "calendar_action": "do_not_create_yet",
  "missing_requirements": ["participant"]
}
```

## 7. Meeting Status Logic

Recommended status labels:

```text
needs_more_context
proposed
email_confirmed
calendar_confirmed
draft_needed
ready_for_user_confirmation
reschedule_requested
write_action_succeeded
write_action_failed
```

Rules:

- Use `calendar_confirmed` only when a matching calendar event is found.
- Use `email_confirmed` when the email thread contains acceptance language such
  as "yes", "works for me", "confirmed", or "that time works", and all
  agreement criteria are satisfied.
- Use `proposed` when a participant suggested a time but there is no acceptance.
- Use `draft_needed` when the user asks to reply with available times.
- Use `ready_for_user_confirmation` when a proposed write action is prepared but
  not executed.
- Use `reschedule_requested` when a later message cancels, postpones, or asks to
  move a previously proposed or confirmed meeting.
- Use `write_action_succeeded` only after a send or calendar create tool returns
  success.
- Use `write_action_failed` when a write tool returns an error.

Recommended `calendar_action` values:

```text
do_not_create_yet
ready_to_create
already_exists
created
creation_failed
```

## 8. Draft Reply Design

A second read-only helper can be added later if draft generation needs to become
more deterministic.

Possible tool:

```python
def draft_scheduling_reply(
    meeting_context_json: str,
    tone: str = "polite",
    include_alternatives: bool = True,
) -> str:
    """Draft a scheduling email from structured meeting context."""
```

This helper should only return draft text. It should not send.

The agent may also generate the draft directly from
`get_meeting_schedule_context` output if the prompt is clear enough.

## 9. Write Action Design

Write actions should be separate from context gathering.

Calendar creation should go through a wrapper instead of calling the raw
calendar provider directly.

```python
def create_confirmed_meeting(
    meeting_context_json: str,
    title: str = "",
    create_meet_link: bool = False,
) -> str:
    """Create a calendar event after explicit user confirmation."""
```

The wrapper should:

1. Parse the JSON returned by `get_meeting_schedule_context`.
2. Reject the request unless `calendar_action = ready_to_create`.
3. Reject the request unless `agreement.ready_to_create_calendar_event = true`.
4. Confirm participant, date, time, meeting intent, and acceptance are present.
5. Re-check calendar context to avoid creating a duplicate event.
6. Call the provider's `create_event` or `create_meet` method.
7. Return structured success or failure.

Scheduling email sending should remain a separate write action:

```python
def send_scheduling_reply(
    to: str,
    subject: str,
    body: str,
) -> str:
    """Send a scheduling reply after explicit user confirmation."""
```

These tools should be treated as high-risk write actions. The agent must ask for
confirmation before calling them.

The final response should distinguish:

```text
Draft prepared.
Calendar event created.
Email sent.
Email failed to send.
```

## 10. Agent Prompt Guidance

The Gmail agent prompt should include a workflow like this:

```text
### Meeting Schedule Workflow

If the user asks to schedule a meeting, check a meeting time, book a meeting, or
reply with availability:
1. Call get_meeting_schedule_context with the contact, thread, requested date,
   requested time, and duration when available.
2. Use the returned structured context as the source of truth.
3. Recommend available slots or explain the current meeting status.
4. If a meeting appears confirmed only in email, say "confirmed in the email
   thread" and do not say "booked".
5. Treat a meeting as ready to add to calendar only when participant, exact date,
   exact time, meeting intent, acceptance, and no later cancellation/reschedule
   are all present.
6. If the user asks for a reply, draft the scheduling reply but do not send it
   unless the user explicitly confirms.
7. If the user asks to book the meeting, prepare the proposed calendar action and
   ask for confirmation before creating it.
8. Report success only after the write tool returns success.
```

## 11. Integration Points

Recommended file structure:

```text
email-agent/
  tools/
    meeting_schedule.py
  prompts/
    gmail_agent.md
    outlook_agent.md
  tests/
    test_meeting_schedule_tool.py
```

Register the tool in:

```text
email-agent/agent.py
```

The first implementation should mirror the Weekly Summary tool pattern:

```text
configure_meeting_schedule(email_tool=email_tool, calendar_tool=calendar_tool, memory_tool=memory)
tools.extend([... get_meeting_schedule_context])
```

## 12. Testing Plan

### Unit Tests

Use mocked email, calendar, and memory tools.

Test cases:

- contact email is resolved from recent email search
- requested date and time are preserved in the output schema
- meeting proposal is detected from meeting language
- email confirmation is detected from acceptance language
- email confirmation is not treated as calendar confirmation
- meeting is ready to create only when participant, date, time, intent, and
  acceptance are all present
- missing date, missing time, or missing acceptance keeps
  `calendar_action = do_not_create_yet`
- later cancellation or reschedule language changes status to
  `reschedule_requested`
- calendar conflicts are returned when found
- available slots are returned when no conflict exists
- missing contact returns `needs_more_context`
- no write actions are performed by the context tool

### Eval / Agent Tests

Natural language prompts:

```text
Help me schedule this meeting.
Check when my recent meeting with the investor is.
Book a meeting with Aiden next week.
Reply with times I am available for this meeting.
Draft a reply offering Monday at 3 PM.
Has this meeting actually been added to my calendar?
```

Expected behavior:

- agent calls the meeting context tool first
- answer includes contact, thread context, and calendar status
- agent distinguishes email-confirmed from calendar-confirmed
- agent explains missing requirements before suggesting calendar creation
- draft requests produce draft text only
- booking requests ask for confirmation before write actions
- success is only claimed after a successful write-tool result

## 13. Recommended Next Step

Add a read-only context tool:

```python
get_meeting_schedule_context(...)
```

This should be implemented before any write-action tool. Once the read-only
context is stable, the team can add separate confirmed write tools for calendar
creation and scheduling email sending.
