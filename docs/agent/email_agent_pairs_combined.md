# Email Agent Query Pairs (Implemented or Near-Implemented Only)

## Overview

This document keeps only the query pairs that are already implemented or reasonably close to implementation in the current email agent codebase. It removes the pairs that are still largely conceptual and not yet supported by dedicated workflows.

The remaining pairs are suitable for evaluation because they align with the current system’s main capabilities:

- inbox triage
- urgency detection
- weekly summarisation
- meeting scheduling support
- follow-up detection
- drafting and writing support
- thread-based reasoning
- contact-aware prioritisation
- newsletter cleanup / unsubscribe confirmation
- meeting availability and scheduling reply support

---

# Implementation Status Check

| Pair | Current status | Notes |
| --- | --- | --- |
| Weekly Summary Query | Completed / strongly supported | Dedicated weekly recap workflow and tool support exist. |
| Meeting Schedule / Book Meeting Query | Strongly supported, not full booking automation | The agent can detect meeting requests, inspect schedule context, recommend slots, and draft scheduling replies. It should not claim a meeting is booked unless a confirmed write action is explicitly available. |
| Writing Style Query | Completed / strongly supported | Drafting flow loads writing style and uses draft confirmation before sending. |
| Urgency Query | Completed / strongly supported | Urgent triage workflow and priority tooling exist. |
| High-Value Email Triage Query | Completed / strongly supported | Supported through email triage scoring, priority categories, and read-only inbox tooling. |
| Awaiting Reply / Blocked-by-Others Query | Completed / strongly supported | Supported by reply-needed detection, `get_unanswered_emails`, and follow-up service logic. |
| Newsletter Cleanup / Unsubscribe Query | Completed / strongly supported | Supports candidate discovery, queue-before-confirm, one-click POST, mailto unsubscribe, manual website fallback, and batch confirmation by text such as `yes`. |
| Bug Review Query | Completed / strongly supported | Dedicated bug review service and fast path exist. |
| Resume Review Query | Completed / strongly supported | Dedicated resume review service and fast path exist; attachment text extraction is still bounded by available metadata/content. |
| Draft Reply Strategy Query | Completed / strongly supported | Supported through thread retrieval, writing style, draft generation, review, and send confirmation. |

For the current 10-pair implementation count, treat contact importance as a supporting signal used by triage, urgency, follow-up, and drafting features, not as a standalone pair.

---

# Fully Implemented or Strongly Supported Pairs

## 1. Weekly Summary Query

### Input
> “Give me a weekly summary of my emails.”

### Intent
The user wants a concise summary of recent email activity so they can quickly understand what happened over the past week.

### Relevant Workspace Sources (Examples)
- `emails.json`
- `thread_state.json`
- weekly summary memory or output files
- email triage records

### Agent Process
1. Retrieve recent emails and threads from the relevant time window.
2. Group activity into meaningful themes or categories.
3. Identify important updates, pending items, and notable changes.
4. Compress the information into a short, readable summary.
5. Return the summary with optional next-step suggestions.

### Output
- Weekly email summary
- Important developments
- Pending or notable actions
- Optional follow-up suggestions

### Example User-Facing Response
> “Here is your weekly email summary:  
> - 3 investor-related conversations were active this week  
> - 2 meeting threads were updated or confirmed  
> - 4 emails were marked as high priority  
> - 1 candidate-related email may require follow-up  
> Would you like a more detailed breakdown by category or only the urgent items?”

---

## 2. Meeting Schedule / Book Meeting Query

### Input
> “Help me schedule this meeting.”
>
> “Check when my recent meeting with the investor is.”
>
> "Book a meeting with Aiden next week."
>
> "Reply with times I am available for this meeting."

### Intent
The user wants the agent to identify, interpret, or assist with meeting-related email threads, including confirmed meeting times or scheduling suggestions.

### Relevant Workspace Sources (Examples)
- `meetings.json`
- `thread_state.json`
- `contacts.csv` / `contacts.json`
- `emails.json`

### Agent Process
1. Detect meeting-related language in the thread.
2. Identify the relevant contact and meeting context.
3. Check whether a meeting has been proposed, confirmed, or rescheduled.
4. Retrieve the latest confirmed or most likely meeting time.
5. If needed, suggest available scheduling options.

### Output
- Meeting time or status
- Scheduling context
- Related participant or thread summary
- Optional next-step suggestion
- Draft scheduling reply when the user wants to respond with available times

### Current Boundary
The current agent can support scheduling and draft the meeting reply, but it should not claim that the meeting has been booked unless a separate confirmed calendar/write step is added or exposed.

### Example User-Facing Response
> “The most recent investor meeting is scheduled for tomorrow at 4:00 PM.  
> It was identified from your recent email thread, and the meeting is currently marked as confirmed.  
> Would you like me to open the related thread, prepare a meeting brief, or suggest a follow-up action?”

---

## 3. Writing Style Query

### Input
> “Write this in my usual style.”
>
> “Draft a reply that sounds like me.”

### Intent
The user wants the agent to adapt generated email replies to match their preferred communication style.

### Relevant Workspace Sources (Examples)
- `writing_style.md`
- prior drafted replies
- current thread context
- style profile memory

### Agent Process
1. Load the user’s stored writing style profile.
2. Analyse the current email’s purpose and audience.
3. Generate a response aligned with the user’s typical tone and structure.
4. Preserve the intended message while adapting phrasing and style.
5. Return a polished draft in the preferred voice.

### Output
- Draft reply in the user’s style
- Tone-aligned wording
- Optional alternative phrasing

### Example User-Facing Response
> “Here is a reply in your usual style:  
> concise, polite, and slightly proactive.  
> Would you like a more formal version or a shorter version for faster sending?”

---

## 4. Urgency Query

### Input
> “Which emails are urgent?”
>
> “Show me what needs attention first.”

### Intent
The user wants the agent to detect and rank emails that require immediate attention.

### Relevant Workspace Sources (Examples)
- `emails.json`
- `email_triage_index.json`
- `priority_inbox.json`
- `thread_state.json`

### Agent Process
1. Analyse recent emails for urgency signals such as deadlines, follow-up pressure, or high-priority senders.
2. Distinguish urgency from low-value noise.
3. Rank urgent emails by severity and action requirement.
4. Summarise why each email is urgent.
5. Return the shortlist in priority order.

### Output
- Urgent email shortlist
- Urgency reasoning
- Suggested next actions
- Priority order

### Example User-Facing Response
> “These emails need attention first:  
> 1. Investor follow-up requesting updated information  
> 2. Candidate thread waiting for confirmation  
> 3. Meeting reschedule requiring a quick response  
> Would you like a one-line action summary for each?”

---

## 5. High-Value Email Triage Query

### Input
> “If I only have 10 minutes, which emails should I read first?”
>
> “Triage my inbox by importance.”

### Intent
The user wants a ranked shortlist of the highest-value emails to review first, based on strategic importance rather than urgency alone.

### Relevant Workspace Sources (Examples)
- `emails.json`
- `email_analysis.json`
- `contacts.json`
- `thread_state.json`
- triage or priority scoring outputs

### Agent Process
1. Analyse recent emails using importance indicators such as sender relevance, business value, deadlines, and thread context.
2. Distinguish strategic importance from raw urgency.
3. Filter out newsletters, low-value notices, and informational clutter.
4. Rank the top emails the user should read first.
5. Provide a short explanation for each selection.

### Output
- Top-priority emails to read now
- Why each email matters
- Suggested reading order
- Optional defer / ignore suggestions

### Example User-Facing Response
> “If you only have 10 minutes, I’d recommend reading these first:  
> 1. Investor follow-up requesting updated traction metrics  
> 2. Candidate email requiring interview confirmation  
> 3. Partnership-style outreach with potential business value  
> I deprioritised newsletters and general announcements.  
> Would you like one-line summaries before opening them?”

---

## 6. Awaiting Reply / Blocked-by-Others Query

### Input
> “Which important conversations are waiting on someone else?”
>
> “Show me emails where I’m waiting for a reply.”

### Intent
The user wants to identify important email threads where progress is currently blocked because another person has not replied yet.

### Relevant Workspace Sources (Examples)
- `thread_state.json`
- `emails.json`
- follow-up records
- `contacts.csv` / `contacts.json`
- interaction timeline data

### Agent Process
1. Identify active and important threads.
2. Detect whether the latest action was taken by the user and whether a reply is still pending.
3. Estimate how long the thread has been waiting.
4. Rank blocked threads by importance and recency.
5. Suggest whether a proactive follow-up is needed.

### Output
- List of blocked or awaiting-reply threads
- Waiting time
- Who is expected to reply
- Whether follow-up is recommended

### Example User-Facing Response
> “There are 3 important threads currently waiting on others:  
> 1. Investor follow-up thread — waiting 5 days for a reply  
> 2. Candidate interview coordination — waiting 3 days on the applicant  
> 3. Partnership discussion — waiting 1 week on confirmation  
> Would you like me to rank which follow-up is most urgent or draft a short reminder message?”

---

# Additional Implemented or Reserve Pairs

## 7. Bug Review Query

### Input
> “Help me check what bugs need to be handled recently.”

### Intent
The user wants a prioritised overview of bug-related tasks derived from recent emails, issue notifications, or technical alerts.

### Relevant Workspace Sources (Examples)
- `emails.json`
- `email_analysis.json`
- `tasks.json`
- `thread_state.json`
- `contacts.json`

### Agent Process
1. Search recent emails and task records for bug-related signals such as:
   - build failed
   - issue opened
   - fix needed
   - failing tests
   - regression
2. Identify which items are still unresolved.
3. Classify them by urgency and action requirement.
4. Rank them by priority.
5. Present the most important bug-related actions.

### Output
- List of unresolved bugs or technical issues
- Urgency / priority
- Linked source
- Suggested next action

### Example User-Facing Response
> “I found 3 bug-related items that may need your attention:  
> 1. Build failure on main branch — high priority  
> 2. Bug report from teammate — medium priority  
> 3. UI issue reported in a recent thread — low priority  
> Would you like me to summarise the bug details or prepare a task list?”

---

## 8. Resume Review Query

### Input
> “Help me check what resumes have been received recently and analyse them.”

### Intent
The user wants the system to retrieve recent candidate-related emails, identify attached resumes, and generate a structured analysis.

### Relevant Workspace Sources (Examples)
- `emails.json`
- `email_analysis.json`
- attachment references from recent emails
- resume PDF files
- `tasks.json`

### Agent Process
1. Identify recent emails related to candidates, applications, or resumes.
2. Detect attached resume files where possible.
3. Extract candidate-related information from the email or attachment context.
4. Summarise the candidate’s profile and notable signals.
5. Optionally compare candidates or suggest next steps.

### Output
- List of recently received resumes
- Candidate summaries
- Key highlights
- Optional recommendation

### Example User-Facing Response
> “I found 4 recent candidate-related emails.  
> Here is a quick overview:  
> - Candidate A — strong backend project experience  
> - Candidate B — stronger frontend profile  
> - Candidate C — balanced full-stack background  
> - Candidate D — more data-oriented experience  
> Would you like a side-by-side comparison or a shortlist suggestion?”

---

## 9. Draft Reply Strategy Query

### Input
> “How should I respond to this email?”

### Intent
The user wants guidance on the best reply strategy, including tone, purpose, and key points, before generating a full draft.

### Relevant Workspace Sources (Examples)
- current email thread
- `thread_state.json`
- `contacts.json`
- writing style profile
- prior interaction history

### Agent Process
1. Analyse the current email intent and relationship context.
2. Identify the most appropriate response goal, such as confirm, clarify, decline, delay, or propose a next step.
3. Recommend an appropriate tone based on the sender relationship.
4. Summarise the key points the reply should include.
5. Optionally offer to generate the full draft.

### Output
- Recommended response strategy
- Suggested tone
- Key points to include
- Optional next-step draft generation

### Example User-Facing Response
> “A good response strategy here would be:  
> - tone: warm and professional  
> - goal: acknowledge the request and offer a clear next step  
> - include: a short update, one concrete answer, and a proactive next action  
> Would you like me to turn that into a polished reply draft?”

---

## 10. Newsletter Cleanup / Unsubscribe Query

### Input
> "Help me unsubscribe from these newsletters."
>
> "Unsubscribe me from Acme News."

### Intent
The user wants the agent to identify newsletter or mailing-list messages and prepare unsubscribe actions without executing them silently.

### Relevant Workspace Sources (Examples)
- `inbox_cache.json`
- Gmail message metadata
- `List-Unsubscribe`
- `List-Unsubscribe-Post`
- unsubscribe preference memory

### Agent Process
1. Search recent synced inbox messages for subscription-like senders and `List-Unsubscribe` metadata.
2. Group candidates by sender, list id, and unsubscribe endpoint.
3. Resolve the selected sender or mailing list into one or more concrete unsubscribe targets.
4. Queue the unsubscribe action for user confirmation instead of executing immediately.
5. After the user replies `yes`, execute one-click POST or mailto unsubscribe when supported.
6. If only a website flow is available, return the URL and explain that manual website confirmation is still required.

### Output
- Candidate mailing lists
- Confirmation request before execution
- Submitted unsubscribe result, or website confirmation link
- Optional archive-existing-message result

### Example User-Facing Response
> "I found 2 matching mailing lists and queued them for confirmation.
> Reply `yes` to unsubscribe, or `no` to cancel."

---

## Notes on Scope

The following previously proposed pairs have been removed from this document because they are still largely conceptual and are not yet clearly supported by the current codebase:

- UNSW Activity Discovery Query
- COMP9900 Student Issue Monitoring Query
- Funding Opportunity / Grant Query
- Partnership / Collaboration Opportunity Query
- Customer / Developer Feedback Query
- other similarly speculative founder-intelligence workflows

This version is intended to stay close to what the current implementation can realistically support.
