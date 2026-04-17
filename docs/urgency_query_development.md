# Urgency Query Development Design

## 1. Purpose

This document describes the intended design for the Urgency Query feature in the
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

`oo-chat` should remain a transport and display layer. Urgency detection should
live in `email-agent` as a read-only tool and prompt workflow.

The goal is:

> Given a user request such as "Which emails are urgent?" or "Show me what needs
> attention first", the agent should inspect recent email activity, identify
> emails that require timely attention, explain why they are urgent, and rank
> them in priority order.

## 2. Design Boundary

Urgency Query should be an independent feature.

It should not be part of Weekly Summary in the first implementation.

Reason:

- Weekly Summary answers: "What happened this week?"
- Urgency Query answers: "What needs attention first?"

Weekly Summary should stay concise. It does not need the full urgency details.

Future integration can be considered later through a lightweight snapshot such
as:

```json
{
  "high_count": 2,
  "medium_count": 3,
  "top_categories": ["security", "meeting"]
}
```

But the first implementation should keep Urgency Query independent.

## 3. Design Constraints

Urgency detection is a read-only workflow.

The tool should not:

- send emails
- draft replies
- archive emails
- mark emails as read
- star emails
- add labels
- create calendar events
- modify memory

The tool should:

- inspect recent emails
- inspect unread emails
- optionally inspect unanswered threads
- classify urgency using explicit evidence
- filter out low-priority automated or promotional emails
- return structured facts for the agent to present

Important boundary:

> The agent should not call a promotional or automated email "urgent" unless
> there is a clear security, account, payment, deadline, or action-required
> signal.

## 4. Desired Design Direction

Urgency Query should be built around a structured urgency tool.

Recommended flow:

```text
User asks which emails are urgent
  -> agent calls get_urgent_email_context
  -> tool gathers recent, unread, and unanswered email context
  -> tool scores emails using urgency signals
  -> tool returns structured urgency ranking
  -> agent explains the ranked list to the user
```

The design principle is:

> The tool should produce structured urgency evidence. The LLM should format and
> explain that evidence.

This reduces hallucination because every urgent item should include a reason and
evidence signal.

## 5. Proposed Tool

### Tool Name

```python
get_urgent_email_context
```

### Proposed Signature

```python
def get_urgent_email_context(
    days: int = 14,
    max_emails: int = 30,
    include_unread: bool = True,
    include_unanswered: bool = True,
    mode: str = "full",
) -> str:
    """Return structured urgency context for recent emails."""
```

### Tool Type

Read-only.

### Modes

The first version should support:

```text
mode="full"
```

This returns the detailed urgency ranking for direct user queries.

A future optional mode can be:

```text
mode="snapshot"
```

This would return only counts and categories if Weekly Summary later wants a
small urgency summary. This should not be connected in the first implementation.

## 6. Responsibilities

The tool should:

1. Search recent emails within `days`.
2. Read unread emails when `include_unread=True`.
3. Read unanswered/follow-up context when `include_unanswered=True`.
4. Parse provider search results into lightweight email records.
5. Score each email using urgency signals.
6. Identify high, medium, low, and ignored items.
7. Attach evidence for each urgency decision.
8. Return a ranked list of urgent emails.
9. Return low-priority or ignored items separately.
10. Include limitations if the provider does not support a needed lookup.

## 7. Urgency Signals

Urgency scoring should combine several types of signals.

Recommended high-urgency signals:

| Signal | Examples |
| --- | --- |
| Security/account risk | `security alert`, `new login`, `password`, `verification`, `unauthorized` |
| Money/payment risk | `invoice overdue`, `payment failed`, `billing`, `refund`, `charge` |
| Explicit urgency | `urgent`, `asap`, `immediately`, `today`, `deadline` |
| Meeting/action deadline | `meeting`, `reschedule`, `confirm`, `reminder`, `tomorrow` |
| Important unanswered thread | unanswered thread from a real person |

Recommended low-priority signals:

| Signal | Examples |
| --- | --- |
| Promotional | `sale`, `offer`, `rewards`, `points`, `discount`, `promotion` |
| Newsletter | `newsletter`, `digest`, `weekly update`, `unsubscribe` |
| Automated code | `one-time code`, `verification code` without account-risk language |
| No-reply sender | `noreply@`, `no-reply@`, `notifications@` |

Some automated emails can still be urgent. For example:

```text
Google security alert
payment failed
new login from unknown device
```

So automated status should reduce urgency only when no strong urgency signal is
present.

## 8. Scoring Design

The first implementation should use deterministic rule-based scoring.

The goal is not to perfectly understand every email. The goal is to provide a
stable first-pass ranking that is explainable and testable.

### Initial Score Model

Each email starts at:

```text
base score = 0
```

Then the tool adds or subtracts points based on signals found in:

- sender
- subject
- preview/body snippet
- unread status
- unanswered/follow-up status
- sender type

### Strong Positive Signals

These signals can make an email urgent by themselves.

| Signal | Score | Category | Examples |
| --- | ---: | --- | --- |
| Account/security risk | +55 | `security` | `security alert`, `new login`, `unauthorized`, `password changed`, `suspicious activity` |
| Payment/billing failure | +45 | `billing` | `payment failed`, `invoice overdue`, `billing issue`, `charge failed` |
| Explicit urgency | +40 | `deadline` | `urgent`, `asap`, `immediately`, `deadline`, `action required` |
| Same-day or tomorrow deadline | +35 | `deadline` | `today`, `tomorrow`, `by EOD`, `before 5 pm` |
| Meeting change or confirmation | +30 | `meeting` | `reschedule`, `confirm a meeting`, `meeting reminder`, `calendar conflict` |

### Supporting Positive Signals

These signals increase urgency, but usually should not make an email high
urgency alone.

| Signal | Score | Notes |
| --- | ---: | --- |
| Email is unread | +15 | Unread matters, but promotional unread emails should still stay low |
| Thread is unanswered | +20 | Stronger when sender looks like a real person |
| Sender looks like a real person | +15 | Personal email, named sender, non-automated sender |
| Known/high-priority contact | +20 | Future improvement using CRM/contact priority |
| Application/resume/job opportunity | +15 | Important, but not always urgent |
| Direct ask detected | +20 | `can you`, `please confirm`, `could you`, question mark |

### Negative Signals

These signals reduce urgency unless a strong positive signal is also present.

| Signal | Score | Notes |
| --- | ---: | --- |
| Promotional/marketing language | -35 | `sale`, `discount`, `offer`, `rewards`, `points`, `promotion` |
| Newsletter/digest language | -30 | `newsletter`, `digest`, `weekly update`, `unsubscribe` |
| Automated sender | -20 | `noreply@`, `no-reply@`, `notifications@`, `marketing@` |
| One-time code only | -25 | Low priority unless combined with suspicious login/security language |
| Receipt/shipping/info-only | -15 | Usually informational unless payment/action failure appears |

### Special Rules

Some rules should override simple scoring:

1. Security override:
   - If account/security risk score is present, do not classify as `ignore`
     even if sender is automated.

2. Verification-code rule:
   - A normal one-time code email should be `low` or `ignore`.
   - A one-time code email with `new login`, `not you`, `suspicious`, or
     `security alert` should become `high`.

3. Promotion rule:
   - Promotional emails should not become urgent only because they are unread.

4. Meeting rule:
   - Meeting reminders are usually `medium`.
   - Meeting reminders with `today`, `tomorrow`, `urgent`, or `reschedule`
     can become `high`.

5. Unanswered-person rule:
   - An unanswered email from a real person should be at least `medium` if it
     includes a direct ask or meeting/action language.

6. Automated-service rule:
   - Automated service emails are normally low, but billing failure, account
     risk, and deadline/action-required signals can raise them to high.

### Suggested Labels

```text
high: score >= 70
medium: score >= 40
low: score >= 15
ignore: score < 15
```

### Initial Category Selection

Each item should receive one main category. Suggested order:

```text
security
billing
deadline
meeting
follow_up
application
promotion
newsletter
verification
general
```

If multiple categories match, choose the highest-priority category from that
order. For example:

```text
"Google security alert with verification code" -> security
"Nike one-time code" -> verification
"Meeting reminder tomorrow" -> meeting
```

### Confidence

The tool can also return a simple confidence label:

```text
high confidence:
  strong signal in subject or sender

medium confidence:
  signal only appears in preview

low confidence:
  weak or conflicting signals
```

The exact numbers and thresholds can be adjusted after testing.

Every scored item should include:

- score
- urgency label
- category
- evidence
- confidence
- suggested action

## 9. Proposed Output Schema

The tool should return JSON as a string.

Example:

```json
{
  "intent": "urgency_query",
  "period": {
    "days": 14
  },
  "source": {
    "recent_query": "newer_than:14d",
    "max_emails": 30,
    "include_unread": true,
    "include_unanswered": true
  },
  "summary": {
    "high_count": 1,
    "medium_count": 2,
    "low_count": 3,
    "ignored_count": 8,
    "has_urgent_items": true
  },
  "urgent_emails": [
    {
      "sender": "Google <no-reply@accounts.google.com>",
      "subject": "Security alert",
      "email_id": "email-1",
      "urgency": "high",
      "score": 90,
      "category": "security",
      "evidence": [
        "subject contains security alert",
        "preview mentions new login",
        "email is unread"
      ],
      "suggested_action": "Review account activity."
    },
    {
      "sender": "Aiden_Yang <945430408@qq.com>",
      "subject": "confirm a meeting",
      "email_id": "email-2",
      "urgency": "medium",
      "score": 55,
      "category": "meeting",
      "evidence": [
        "subject mentions confirm",
        "preview mentions meeting",
        "sender looks like a real person"
      ],
      "suggested_action": "Confirm attendance or reply if needed."
    }
  ],
  "low_priority": [
    {
      "sender": "Nike <nike@official.nike.com>",
      "subject": "Make your move",
      "email_id": "email-3",
      "urgency": "ignore",
      "score": 0,
      "category": "promotion",
      "evidence": [
        "promotional language detected"
      ],
      "suggested_action": "No immediate action needed."
    }
  ],
  "limitations": [
    "This tool ranks urgency from available metadata and previews.",
    "It does not modify email state."
  ]
}
```

## 10. Agent Response Guidance

When the user asks:

```text
Which emails are urgent?
Show me what needs attention first.
```

The agent should:

1. Call `get_urgent_email_context`.
2. Use the returned ranking as the source of truth.
3. Show high urgency first, then medium.
4. Briefly explain why each item is urgent.
5. Mention low-priority items only if useful.
6. Do not draft or send replies unless the user asks separately.

Recommended response style:

```text
These emails need attention first:

1. Google security alert — high
   Reason: new login/account security signal.
   Suggested action: review account activity.

2. Aiden_Yang meeting confirmation — medium
   Reason: meeting confirmation request from a real person.
   Suggested action: reply or confirm attendance.

I deprioritized Nike promotional/code emails because they appear automated and
do not require a reply.
```

## 11. Relationship With Weekly Summary

First implementation:

```text
Urgency Query is independent.
Weekly Summary does not call it.
```

Future optional integration:

```python
get_weekly_email_activity(include_urgency_snapshot=True)
```

If added later, Weekly Summary should only use a light snapshot:

```json
{
  "high_count": 1,
  "medium_count": 2,
  "top_categories": ["security", "meeting"]
}
```

Weekly Summary should not include the full urgent email list by default.

## 12. Edge Cases

### Automated Security Emails

Automated security alerts should still be high urgency if account-risk signals
are present.

### Verification Codes

One-time verification codes are usually low priority unless they suggest
unexpected login or suspicious activity.

### Promotional Emails

Promotional emails should usually be ignored even if unread.

### Meeting Reminders

Meeting reminders should usually be medium urgency unless there is a same-day or
explicit deadline signal.

### Unclear Sender

If sender importance is unclear, use content signals and mark confidence lower.

## 13. Testing Plan

Recommended tests:

1. Security alert is high urgency.
2. Meeting confirmation from a real person is medium urgency.
3. Promotional email is ignored or low priority.
4. One-time code is ignored unless account-risk language exists.
5. Unread status increases score but does not make promotions urgent by itself.
6. Unanswered thread increases urgency for real-person senders.
7. Tool returns valid JSON.
8. Tool does not call send/reply/archive/mark-read methods.

## 14. Implementation Checklist

Recommended implementation order:

1. Create `email-agent/tools/urgency.py`.
2. Add `configure_urgency(email_tool, memory_tool=None)`.
3. Add `get_urgent_email_context`.
4. Export the tool from `email-agent/tools/__init__.py`.
5. Register the tool in `email-agent/agent.py`.
6. Add Urgency Query workflow instructions to Gmail and Outlook prompts.
7. Add focused tests in `email-agent/tests/test_urgency_tool.py`.
8. Rebuild Docker before testing through `oo-chat`.

## 15. Success Criteria

Urgency Query is successful when:

- urgent emails are ranked consistently
- each urgent item includes evidence
- promotional and automated noise is deprioritized
- security/account-risk emails are not missed
- the tool is read-only
- the agent does not draft or send unless the user separately asks
- Weekly Summary remains independent in the first implementation
