# Weekly Summary Development Design

## 1. Purpose

This document describes how the Weekly Summary feature should work in the current
`9900-H16C-Cake` project.

The current project architecture is:

```text
oo-chat frontend
  -> Next.js API route
  -> hosted email-agent backend
  -> Gmail / Calendar / Memory tools
  -> final agent response
  -> oo-chat display
```

`oo-chat` is mainly responsible for message transport and display. The actual
email reasoning happens inside `email-agent`.

For Weekly Summary, the goal is:

> Given a user request such as "do weekly summary" or "Give me a weekly summary
> of my emails", the agent should inspect recent email activity, identify
> important themes, unread or urgent messages, meeting-related activity,
> follow-up status, and calendar context, then return a concise summary.

## 2. Design Constraints

The current Weekly Summary behavior has several limitations:

- There is no dedicated `get_weekly_email_activity` or `weekly_summary` tool.
- The agent may choose different tool call sequences for similar user requests.
- The output format is not guaranteed to be consistent.
- Important categories are inferred by the LLM rather than produced by a stable
  data-processing layer.
- Thread grouping is limited.
- A meeting confirmed in an email thread may be described as scheduled even if no
  matching calendar event exists.
- There is no explicit schema for weekly activity data.
- There are no focused tests for Weekly Summary behavior.

The most important boundary:

> The agent should not claim a meeting is booked in the calendar unless a
> calendar event was actually found or created. If the evidence only comes from
> an email conversation, the agent should say the meeting appears confirmed in
> the email thread.

## 3. Desired Design Direction

Weekly Summary should be implemented as a read-only aggregation workflow.

The recommended design is:

```text
User asks for weekly summary
  -> agent calls a dedicated weekly activity tool
  -> tool gathers structured facts from Gmail / Calendar / follow-up tools
  -> tool returns structured summary data
  -> LLM formats the final answer for the user
```

The key design principle is:

> Tools should gather reliable structured facts. The LLM should format and
> explain those facts.

The tool should not try to produce the final polished prose by itself. It should
return enough structured information for the agent to generate different output
styles, such as:

- normal weekly summary
- clean bullet-point report
- short executive summary
- urgent-only summary
- meeting-only summary

## 4. Proposed Tool

### Tool Name

```python
get_weekly_email_activity
```

### Proposed Signature

```python
def get_weekly_email_activity(
    days: int = 7,
    max_emails: int = 50,
    include_calendar: bool = True,
    include_unanswered: bool = True,
) -> str:
    """Collect structured email activity for the last N days."""
```

### Tool Type

Read-only.

The tool should not:

- send emails
- archive emails
- mark emails as read
- create calendar events
- unsubscribe from newsletters
- modify memory unless explicitly designed to cache summary data later

### Responsibilities

The tool should:

1. Calculate the date range.
2. Search Gmail for recent emails in that range.
3. Count total and unread emails.
4. Group emails into useful categories.
5. Identify important or urgent-looking messages.
6. Identify meeting-related conversations.
7. Identify application or resume-related activity when visible.
8. Identify promotional or newsletter-like messages.
9. Optionally call unanswered email detection.
10. Optionally call calendar lookup for upcoming events.
11. Return structured data to the agent.

## 5. Proposed Output Schema

The tool can return JSON as a string, or a clearly structured text block. JSON is
preferred because it is easier for the agent to consume consistently.

Example:

```json
{
  "period": {
    "days": 7,
    "start_date": "2026-04-10",
    "end_date": "2026-04-17"
  },
  "counts": {
    "total_emails": 20,
    "unread_emails": 4,
    "senders": 6
  },
  "themes": [
    {
      "name": "Security alerts",
      "importance": "high",
      "email_count": 6,
      "summary": "Multiple Google account security alerts and one X login alert.",
      "items": [
        {
          "sender": "Google",
          "subject": "Security alert",
          "status": "unread",
          "reason": "New login or account authorization activity"
        }
      ]
    },
    {
      "name": "Meeting scheduling",
      "importance": "medium",
      "email_count": 7,
      "summary": "Several threads discussed meetings and coffee chats.",
      "items": [
        {
          "sender": "zenglin0813@gmail.com",
          "subject": "meeting urgent",
          "status": "email_confirmed",
          "calendar_event_found": false,
          "reason": "The email thread includes a confirmation reply"
        }
      ]
    }
  ],
  "unanswered": [],
  "calendar": {
    "upcoming_events_found": false,
    "events": []
  },
  "suggested_priorities": [
    "Review Google and X login alerts.",
    "Add email-confirmed meetings to calendar if needed."
  ],
  "limitations": [
    "Calendar confirmation is separate from email-thread confirmation."
  ]
}
```

## 6. Category Logic

The first version can use simple rule-based grouping before asking the LLM to
format the result.

Recommended categories:

| Category | Signals |
| --- | --- |
| Security alerts | `security`, `login`, `authorization`, `Google`, `X`, `account` |
| Meeting scheduling | `meeting`, `schedule`, `available`, `coffee chat`, `tomorrow`, date/time terms |
| Applications / resumes | `application`, `job`, `resume`, `CV`, `candidate`, `opportunity` |
| Follow-up needed | unanswered email tool result, direct asks, deadlines |
| Newsletters / promotions | `unsubscribe`, marketing senders, rewards, newsletter-like senders |
| General FYI | low-action informational emails |

The category logic does not need to be perfect at first. It should provide a
stable first pass that the LLM can refine.

## 7. Meeting Status Logic

Meeting-related summary needs careful wording.

Recommended status labels:

```text
proposed
email_confirmed
calendar_confirmed
unclear
```

Rules:

- Use `calendar_confirmed` only if a matching calendar event is found.
- Use `email_confirmed` if the email thread contains acceptance language such as
  "yes", "works for me", or "confirmed".
- Use `proposed` if one side suggested times but no clear acceptance is visible.
- Use `unclear` if the email preview is insufficient.

The final response should say:

```text
This appears confirmed in the email thread, but I did not find a matching
calendar event.
```

instead of:

```text
This meeting is booked.
```

unless the calendar confirms it.

## 8. Agent Prompt Guidance

The Gmail agent prompt should eventually include a small workflow section:

```text
### Weekly Summary Workflow

If the user asks for a weekly summary, weekly report, or summary of recent email
activity:
1. Call get_weekly_email_activity(days=7) unless the user specifies another time
   range.
2. Use the returned structured data as the source of truth.
3. Include key themes, important emails, unread items, follow-up status, and
   meeting/calendar status.
4. Do not claim a meeting is booked unless the tool reports
   calendar_confirmed.
5. If the user asks for a different format, reuse the existing facts and only
   reformat the answer.
```

This keeps the agent behavior stable while still allowing flexible natural
language formatting.

## 9. Integration Points

The current backend agent is assembled in:

```text
email-agent/agent.py
```

A future implementation could add the new tool in one of two ways.

### Option A: Simple First Version

Add the tool directly in `agent.py`.

Pros:

- fastest to implement
- easy to register with the existing agent
- good for early prototype

Cons:

- `agent.py` may become too large over time

### Option B: Cleaner Service-Based Version

Create a small service module:

```text
email-agent/services/weekly_summary.py
```

Then import and register the tool in `agent.py`.

Pros:

- cleaner architecture
- easier to test
- better if more features will be added later

Cons:

- slightly more setup

Recommended direction:

> Use Option B if the team plans to add multiple feature-specific workflows such
> as resume review, bug review, and unsubscribe. Use Option A only for a quick
> prototype.

## 10. Testing Plan

Weekly Summary should be tested at two levels.

### Unit Tests

Test the aggregation logic with mocked email data.

Examples:

- security emails are grouped under Security alerts
- meeting emails are grouped under Meeting scheduling
- unread count is calculated correctly
- `email_confirmed` is not treated as `calendar_confirmed`
- promotional emails are deprioritized
- empty inbox returns a useful no-activity summary

### Eval / Agent Tests

Natural language test prompts:

```text
do weekly summary
Give me a weekly summary of my emails.
Summarize my email activity from the last 7 days.
Turn it into a clean bullet-point weekly report.
Give me a short executive summary version.
Only show urgent items from this weekly summary.
```

Expected behavior:

- agent calls the weekly activity tool
- answer includes time period
- answer includes main categories
- answer includes unread or urgent items when present
- answer does not invent calendar bookings
- follow-up formatting requests reuse the same facts

## 11. Recommended Next Step

The recommended next step is to add a read-only aggregation tool:

```python
get_weekly_email_activity(days=7, max_emails=50)
```

This tool should return structured facts, not final prose. The agent should then
use those facts to generate the final weekly summary in whatever format the user
requests.

This approach keeps the current good user experience while making the feature
more stable, testable, and easier to evaluate.
