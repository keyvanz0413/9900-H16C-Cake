# Weekly Summary Workflow Test Matrix

This document maps user phrasing to the expected agent workflow for the weekly
summary feature. Use it when turning the current tool behavior into a skill.

Current date used in recent observations: 2026-04-18.

## Source Of Truth

Main agent-facing tool:

```text
get_weekly_email_activity(days=7, max_emails=50, include_calendar=True, include_unanswered=True)
```

In live agent runs, the LLM has often chosen `max_emails=200`. That is allowed by
the function clamp and still uses the same workflow.

Backend provider calls inside the tool:

```text
1. email.search_emails(query=f"newer_than:{days}d", max_results=max_emails)
2. email.get_unanswered_emails(within_days=days, max_results=20)
3. calendar.list_events(days_ahead=days)
```

Fallbacks:

```text
email.get_unanswered_emails(older_than_days=days, max_results=20)
calendar.get_today_events()
```

The tool is read-only. Weekly summary should not call `send`, `mark_read`,
`archive`, `create_event`, `create_meet`, or unsubscribe/modify methods.

## Implementation Workflow

Default successful flow:

```text
User asks for weekly summary
-> agent calls get_weekly_email_activity(days=7)
-> weekly tool calls email.search_emails("newer_than:7d")
-> weekly tool parses provider text into email records
-> weekly tool categorizes themes
-> weekly tool calls email.get_unanswered_emails(...)
-> weekly tool calls calendar.list_events(...)
-> weekly tool returns JSON
-> agent formats final answer from JSON
```

If `include_unanswered=False`:

```text
search_emails only, plus optional calendar depending on include_calendar
```

If `include_calendar=False`:

```text
search_emails plus optional unanswered, no calendar provider method
```

If no email provider is configured:

```text
No provider backend calls.
Returns JSON limitation: "No email provider tool is configured."
```

If no calendar provider is configured:

```text
Still calls email provider methods.
Adds JSON limitation: "No calendar provider tool is configured."
```

## Real Observed Runs

Observed from `.co/evals` and Docker logs.

## Test Run: 2026-04-18

These were run through `oo-chat` -> `/api/chat` -> `email-agent /input`, then
verified with Docker logs and `.co/evals/*.yaml`.

### Prompt-Level Results

| Prompt | Observed agent tools | Result |
| --- | --- | --- |
| `do weekly summary` | `get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)`, then `read_inbox(last=50)`, `get_sent_emails(max_results=50)`, `list_events(days_ahead=7, max_results=20)`, `get_unanswered_emails(within_days=7, max_results=20)` | Partial failure: weekly tool was called, but agent continued with fallback tools. A skill should avoid extra provider calls after weekly tool succeeds. |
| `summarize my email activity this week` | `get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)` | Pass |
| `weekly report for my emails please` | `get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)` | Pass |
| `executive-style weekly report` | `get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)`, then `list_events(days_ahead=7)`, `list()`, `count_unread()` | Partial failure: weekly tool was called, but extra tools were used. |
| `这周邮件帮我总结一下` | `get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)` | Pass |
| `give me a 14-day email summary` | `get_weekly_email_activity(days=14, max_emails=400, include_calendar=True, include_unanswered=True)` | Pass at agent level; internal tool clamps max emails to 200. |
| `last two weeks inbox recap` | `get_weekly_email_activity(days=14, max_emails=200, include_calendar=False, include_unanswered=True)` | Pass for range; note calendar was omitted. If the skill requires calendar status, force `include_calendar=True`. |
| `weekly recap, tell me what needs follow-up` | `get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)`, `get_urgent_email_context(days=7, max_emails=100, ...)`, `get_today_events()`, `list_events(days_ahead=7)` | Partial failure: follow-up phrasing caused extra urgency/calendar calls. |
| `show my latest 10 emails` | `read_inbox(last=10, unread=False)` | Correct negative case. |
| `do I have any urgent email?` | `get_urgent_email_context(days=7, max_emails=25, include_unread=True, include_unanswered=True, ...)` | Correct negative case. |

### Internal Provider Trace

Directly tracing `get_weekly_email_activity(days=7, max_emails=50)` with the real
configured providers produced:

```text
email.search_emails(query="newer_than:7d", max_results=50)
email.get_unanswered_emails(within_days=7, max_results=20)
calendar.list_events(days_ahead=7)
```

The returned focus data was:

```text
total_emails=20
unread_emails=4
senders=8
unanswered detected=false
calendar upcoming_events_found=false
```

Direct branch traces:

| Direct function call | Observed provider calls |
| --- | --- |
| `get_weekly_email_activity(days=14, max_emails=400, include_calendar=True, include_unanswered=True)` | `email.search_emails(query="newer_than:14d", max_results=200)`, `email.get_unanswered_emails(within_days=14, max_results=20)`, fallback `email.get_unanswered_emails(older_than_days=14, max_results=20)`, `calendar.list_events(days_ahead=14)` |
| `get_weekly_email_activity(days=14, max_emails=200, include_calendar=False, include_unanswered=True)` | `email.search_emails(query="newer_than:14d", max_results=200)`, `email.get_unanswered_emails(within_days=14, max_results=20)` |
| `get_weekly_email_activity(days=7, max_emails=50, include_calendar=False, include_unanswered=False)` | `email.search_emails(query="newer_than:7d", max_results=50)` |

Important observation: `.co/evals` records agent-level tool calls only. It does
not show provider calls made inside `get_weekly_email_activity`, so internal
provider coverage needs direct tracing or added instrumentation.

### Correct Current Workflow

Prompt:

```text
do weekly summary
```

Observed agent tool:

```text
get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)
```

Expected backend provider calls:

```text
email.search_emails(query="newer_than:7d", max_results=200)
email.get_unanswered_emails(within_days=7, max_results=20)
calendar.list_events(days_ahead=7)
```

### Format Variant That Still Used Weekly Tool

Prompt:

```text
executive-style weekly report
```

Observed agent tool:

```text
get_weekly_email_activity(days=7, max_emails=200, include_calendar=True, include_unanswered=True)
```

This is the preferred behavior for a new weekly-report phrasing.

### Older / Undesired Legacy Workflow

Prompt:

```text
turn it into a clean bullet-point weekly report
```

Observed older tool sequence:

```text
read_inbox(last=10, unread=False)
search_emails(query="newer_than:7d", max_results=50)
search_emails(query="Wenyu Ding OR Wenyu OR from:(Wenyu) OR to:(Wenyu)", max_results=10)
send(...)
search_emails(query="newer_than:7d", max_results=50)
get_unanswered_emails(within_days=7, max_results=20)
get_upcoming_meetings(days_ahead=7)
```

This should be treated as a regression or old behavior. A weekly summary skill
should force the read-only weekly tool and should never send email while
summarizing.

### Follow-up Formatting

Prompt after a summary:

```text
give me weekly email summary
```

The eval file records `get_weekly_email_activity(...)`. The plain agent log for
that turn did not show a separate tool line, likely because of cached or compacted
context. When validating, prefer the eval YAML for `tools_called`, then confirm
Docker logs if needed.

For pure follow-up formatting prompts like "make it shorter", expected behavior is
no new provider calls; reuse the previous structured facts.

## Web Prompt Test Set

Run these one by one in `oo-chat` at `http://localhost:3300`. After each prompt,
check `.co/evals/<slug>.yaml` and Docker logs.

### A. Weekly Summary Triggers

All of these should call `get_weekly_email_activity`. They should not directly call
`read_inbox`, `get_sent_emails`, `send`, or calendar write methods.

| ID | User prompt | Expected agent tool | Expected weekly args |
| --- | --- | --- | --- |
| WS-01 | `do weekly summary` | `get_weekly_email_activity` | `days=7`, calendar true, unanswered true |
| WS-02 | `give me weekly email summary` | `get_weekly_email_activity` | `days=7` |
| WS-03 | `summarize my email activity this week` | `get_weekly_email_activity` | `days=7` |
| WS-04 | `what happened in my inbox this week?` | `get_weekly_email_activity` | `days=7` |
| WS-05 | `weekly report for my emails please` | `get_weekly_email_activity` | `days=7` |
| WS-06 | `catch me up on this week's emails` | `get_weekly_email_activity` | `days=7` |
| WS-07 | `make me a weekly email recap` | `get_weekly_email_activity` | `days=7` |
| WS-08 | `executive-style weekly report` | `get_weekly_email_activity` | `days=7` |
| WS-09 | `weekly inbox digest with action items` | `get_weekly_email_activity` | `days=7` |
| WS-10 | `这周邮件帮我总结一下` | `get_weekly_email_activity` | `days=7` |
| WS-11 | `帮我做一个邮箱周报` | `get_weekly_email_activity` | `days=7` |
| WS-12 | `最近一周邮件有什么重点？` | `get_weekly_email_activity` | `days=7` |

Expected backend calls for WS-01 to WS-12:

```text
email.search_emails(query="newer_than:7d", max_results=<50 or 200>)
email.get_unanswered_emails(within_days=7, max_results=20)
calendar.list_events(days_ahead=7)
```

### B. Range Variants

These test whether the LLM maps natural language ranges into `days`.

| ID | User prompt | Expected agent tool | Expected days | Backend search query |
| --- | --- | --- | --- | --- |
| RV-01 | `summarize my emails from the last 3 days` | `get_weekly_email_activity` | `3` | `newer_than:3d` |
| RV-02 | `give me a 14-day email summary` | `get_weekly_email_activity` | `14` | `newer_than:14d` |
| RV-03 | `last two weeks inbox recap` | `get_weekly_email_activity` | `14` | `newer_than:14d` |
| RV-04 | `monthly-ish email recap for the last 30 days` | `get_weekly_email_activity` | `30` | `newer_than:30d` |
| RV-05 | `summarize the last 90 days of email activity` | `get_weekly_email_activity` | `90` | `newer_than:90d` |
| RV-06 | `summarize the last 100 days of email activity` | `get_weekly_email_activity` | clamped to `90` | `newer_than:90d` |
| RV-07 | `summarize yesterday through today in my inbox` | `get_weekly_email_activity` or daily tool | `1` or `2` | verify actual |
| RV-08 | `what changed in email since Monday?` | likely `get_weekly_email_activity` | computed by LLM | verify actual |

### C. Format-Only Follow-ups

Run these immediately after a successful weekly summary. These should not fetch
provider data again. They should reuse the previous facts unless the user asks for
a fresh summary.

| ID | User prompt | Expected workflow |
| --- | --- | --- |
| FF-01 | `make it shorter` | no new tool call |
| FF-02 | `turn that into bullet points` | no new tool call |
| FF-03 | `用中文总结一下刚才的周报` | no new tool call |
| FF-04 | `make it executive style` | no new tool call |
| FF-05 | `only show action items` | no new tool call |
| FF-06 | `give me a Slack-ready version` | no new tool call |
| FF-07 | `now refresh it with current data` | call `get_weekly_email_activity` again |
| FF-08 | `重新查一遍再总结` | call `get_weekly_email_activity` again |

### D. Calendar And Follow-up Coverage

These prompts should still use the weekly tool, but the output should emphasize
specific sections from the returned JSON.

| ID | User prompt | Expected agent tool | Expected output focus |
| --- | --- | --- | --- |
| CF-01 | `weekly email summary including calendar status` | `get_weekly_email_activity` | calendar raw result / found status |
| CF-02 | `weekly email summary, focus on meetings` | `get_weekly_email_activity` | meeting theme plus calendar status |
| CF-03 | `weekly recap, tell me what needs follow-up` | `get_weekly_email_activity` | unanswered section |
| CF-04 | `这周有没有没回的邮件？顺便总结一下` | `get_weekly_email_activity` | unanswered section |
| CF-05 | `weekly summary but don't book anything` | `get_weekly_email_activity` | no write tools |
| CF-06 | `weekly summary and check if meetings are actually on calendar` | `get_weekly_email_activity` | calendar status; no create event |

Expected backend calls:

```text
email.search_emails(...)
email.get_unanswered_emails(...)
calendar.list_events(...)
```

### E. Negative / Boundary Prompts

These are useful to confirm the skill does not over-trigger.

| ID | User prompt | Expected behavior |
| --- | --- | --- |
| NB-01 | `show my latest 10 emails` | should use inbox/search tools, not weekly summary |
| NB-02 | `do I have urgent email?` | should use urgency tool, not weekly summary |
| NB-03 | `draft a reply to the latest email` | should use draft reply flow, not weekly summary |
| NB-04 | `schedule a meeting from my recent email` | should use meeting schedule flow, not weekly summary |
| NB-05 | `learn my writing style` | should use writing style tool, not weekly summary |
| NB-06 | `send the weekly summary to Aiden` | should first produce/confirm; do not send automatically |
| NB-07 | `archive low priority emails from the weekly summary` | should refuse or ask confirmation; weekly summary itself is read-only |
| NB-08 | `mark all weekly-summary emails as read` | should not modify as part of weekly summary |

## Direct Backend Branch Tests

These can be tested with fake providers or by unit tests. They cover all possible
backend method branches inside `get_weekly_email_activity`.

| ID | Setup | Function call | Expected backend calls |
| --- | --- | --- | --- |
| DB-01 | email + calendar with `list_events` | default args | `search_emails`, `get_unanswered_emails(within_days)`, `list_events` |
| DB-02 | email + no calendar | default args | `search_emails`, `get_unanswered_emails`; no calendar method |
| DB-03 | email + calendar only has `get_today_events` | default args | `search_emails`, `get_unanswered_emails`, `get_today_events` |
| DB-04 | email without `get_unanswered_emails` | default args | `search_emails`, no unanswered provider call |
| DB-05 | email `get_unanswered_emails` supports only `older_than_days` | default args | `search_emails`, failed within-days attempt, fallback `older_than_days` |
| DB-06 | no email provider | default args | no backend provider calls |
| DB-07 | `include_unanswered=False` | default calendar | `search_emails`, `list_events`; no unanswered call |
| DB-08 | `include_calendar=False` | default email | `search_emails`, `get_unanswered_emails`; no calendar call |
| DB-09 | `include_calendar=False`, `include_unanswered=False` | default email | `search_emails` only |
| DB-10 | `days=0` | default providers | clamped to `1`; query `newer_than:1d` |
| DB-11 | `days=1000` | default providers | clamped to `90`; query `newer_than:90d` |
| DB-12 | `max_emails=999` | default providers | clamped to `200`; search max results `200` |
| DB-13 | provider search raises exception | default providers | raw email result starts with `Error:`; no crash |
| DB-14 | calendar list raises exception | default providers | calendar raw result starts with `Error:`; no crash |
| DB-15 | provider returns `Found 0 email(s)` | default providers | zero counts, empty themes |

## Method Coverage Checklist

Use this to ensure every backend method has at least 10 prompt-level or branch-level
tests across manual and direct tests.

### `get_weekly_email_activity`

Covered by WS-01 through WS-12, RV-01 through RV-08, CF-01 through CF-06.

Minimum 10:

```text
WS-01, WS-02, WS-03, WS-04, WS-05,
WS-06, WS-07, WS-08, WS-09, WS-10
```

### `email.search_emails`

Covered by every successful weekly tool call plus DB branch tests.

Minimum 10:

```text
WS-01, WS-02, WS-03, WS-04, WS-05,
RV-01, RV-02, RV-03, RV-04, DB-09
```

### `email.get_unanswered_emails`

Covered by weekly default runs and branch tests.

Minimum 10:

```text
WS-01, WS-02, WS-03, WS-04, WS-05,
CF-01, CF-02, CF-03, CF-04, DB-05
```

Also explicitly test skipped behavior:

```text
DB-04, DB-07, DB-09
```

### `calendar.list_events`

Covered by weekly default runs and calendar-focused prompts.

Minimum 10:

```text
WS-01, WS-02, WS-03, WS-04, WS-05,
CF-01, CF-02, CF-05, CF-06, DB-01
```

Also explicitly test skipped/fallback behavior:

```text
DB-02, DB-03, DB-08, DB-09
```

### `calendar.get_today_events`

This is a fallback only. It cannot be reliably forced from user phrasing if the
configured calendar provider supports `list_events`. Test it with a fake calendar
that has `get_today_events` but no `list_events`.

Minimum branch set:

```text
DB-03 repeated with days=1, 3, 7, 14, 30, 90
DB-03 with include_unanswered=True
DB-03 with include_unanswered=False
DB-03 with empty email results
DB-03 with non-empty email results
```

## Log Verification

After each web prompt, check:

```bash
docker compose logs --tail=120 email-agent
```

Useful lines look like:

```text
[co] > "do weekly summary"
[co]   ▸ get_weekly_email_activity(days=7, max_emails=200, ...) [OK]
[co]   /app/.co/evals/do_weekly_summary.yaml
```

Then inspect the eval YAML:

```bash
sed -n '1,220p' email-agent/.co/evals/<slug>.yaml
```

Look for:

```text
tools_called:
- get_weekly_email_activity(...)
```

If `tools_called` contains `send(...)`, `mark_read(...)`, `archive(...)`,
`create_event(...)`, or `create_meet(...)`, treat that as a weekly-summary
workflow failure.

## Skill Rule Draft

```text
When the user asks for a weekly summary, weekly report, weekly recap, recent email
activity summary, or Chinese equivalents like "邮箱周报" / "总结这周邮件":

1. Call get_weekly_email_activity(days=7) unless the user specifies another range.
2. Use the returned JSON as the only source of truth.
3. Include period, counts, main themes, unread items, unanswered/follow-up status,
   calendar status, and suggested priorities.
4. If a meeting has status email_confirmed, say it appears confirmed in email,
   not booked in calendar.
5. Do not call write tools. Do not send, archive, mark read, create events, or
   unsubscribe while summarizing.
6. For immediate format-only follow-ups, reuse the previous facts and do not fetch
   again unless the user asks to refresh/recheck.
```
