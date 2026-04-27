# Email Agent Query Pairs (Implemented or Near-Implemented Only)

## Overview

This document keeps only the query pairs that are already implemented or reasonably close to implementation in the current email agent codebase. It removes the pairs that are still largely conceptual and not yet supported by dedicated workflows.

The remaining pairs are suitable for evaluation because they align with the current system's main capabilities:

- weekly email summary
- email drafting
- writing style learning
- urgency detection
- meeting scheduling
- unsubscribe email

---

# Implementation Status Check

- **Weekly Email Summary Query**: Completed / strongly supported - Dedicated weekly recap workflow and tool support exist.
- **Email Drafting Query**: Completed / strongly supported - Drafting flow loads context and uses confirmation before sending.
- **Writing Style Learning Query**: Completed / strongly supported - Style profile memory and adaptation exist.
- **Urgency Detection Query**: Completed / strongly supported - Urgent triage workflow and priority tooling exist.
- **Meeting Scheduling Query**: Strongly supported, not full booking automation - The agent can detect meeting requests, inspect schedule context, recommend slots, and draft scheduling replies. It should not claim a meeting is booked unless a confirmed write action is explicitly available.
- **Unsubscribe Email Query**: Completed / strongly supported - Supports candidate discovery, queue-before-confirm, one-click POST, mailto unsubscribe, manual website fallback, and batch confirmation by text such as `yes`.

For the current 6-pair implementation count, treat supporting signals as part of the core features, not as standalone pairs.

---

# Fully Implemented or Strongly Supported Pairs

## 1. Weekly Email Summary Query

### Input
> "Give me a weekly summary of my emails."

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
> "Here is your weekly email summary:  
> - 3 investor-related conversations were active this week  
> - 2 meeting threads were updated or confirmed  
> - 4 emails were marked as high priority  
> - 1 candidate-related email may require follow-up  
> Would you like a more detailed breakdown by category or only the urgent items?"

---

## 2. Email Drafting Query

### Input
> "Draft a reply to ‘whose’ email."

### Intent
The user wants the agent to generate a draft email reply based on the current thread and context.

### Relevant Workspace Sources (Examples)
- current email thread
- `thread_state.json`
- `contacts.json`
- writing style profile

### Agent Process
1. Analyse the current email thread for context and intent.
2. Load relevant contact information and writing style.
3. Generate a draft reply aligned with the user's preferences.
4. Provide the draft for review and confirmation before sending.

### Output
- Draft email reply
- Key points included
- Optional alternative versions

### Example User-Facing Response
> "Here is a draft reply based on the thread:  
> 'Thank you for your update. I will review the details and get back to you by end of day.'  
> Would you like to edit this, add attachments, or send it as is?"

---

## 3. Writing Style Learning Query(Before use agent, Recommend prioritized operation)

### Input
> "Learn my writing style "

### Intent
The user wants the agent to analyse past emails to learn and adapt to their preferred writing style.

### Relevant Workspace Sources (Examples)
- `emails.json`
- prior drafted replies
- `writing_style.md`
- style profile memory

### Agent Process
1. Retrieve and analyse a sample of the user's sent emails.
2. Identify patterns in tone, structure, and phrasing.
3. Update or create a writing style profile.
4. Apply the learned style to future drafts.

### Output
- Updated writing style profile
- Summary of learned characteristics
- Example of style application

### Example User-Facing Response
> "I've analysed your recent emails and updated your writing style profile:  
> - Tone: Professional and concise  
> - Structure: Direct opening, key points, clear call to action  
> - Phrasing: Uses 'I' for personal touch, avoids jargon  
> This will be applied to future drafts. Would you like to see an example?"

---

## 4. Urgency Detection Query

### Input
> "Which emails are urgent?"

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

### Output
- Urgent email shortlist
- Urgency reasoning
- Suggested next actions
- Priority order

### Example User-Facing Response
> "These emails need attention first:  
> 1. Investor follow-up requesting updated information  
> 2. Candidate thread waiting for confirmation  
> 3. Meeting reschedule requiring a quick response  
> Would you like a one-line action summary for each?"

---

## 5. Meeting Scheduling Query

### Input
> "Help me schedule this meeting."

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
> "The most recent investor meeting is scheduled for tomorrow at 4:00 PM.  
> It was identified from your recent email thread, and the meeting is currently marked as confirmed.  
> Would you like me to open the related thread, prepare a meeting brief, or suggest a follow-up action?"

---

## 6. Unsubscribe Email Query

### Input
> "Help me unsubscribe from these newsletters."

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