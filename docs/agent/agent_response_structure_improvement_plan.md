# Agent Response Structure Improvement Plan

## Current Status

Status: **planned / UX refinement**.

The email agent already has several implemented fast-path workflows, including resume review, bug review, meeting reservation review, newsletter unsubscribe handling, daily summaries, and weekly recap style inbox summaries. These workflows are useful, but the user-facing answers can feel inconsistent:

- some replies are compact lists
- some replies mix paragraphs and numbered items
- some replies repeat detail labels in a way that feels visually noisy
- long summaries can become hard to scan in a chat bubble
- frontend markdown rendering can split numbered lists when each item has multi-line details

This plan describes how to make agent answers more structured, predictable, and pleasant to read without changing the underlying mailbox tools or business logic.

---

## 1. Goal

Improve the user experience of chat responses by making aggregation-style answers easier to scan and act on.

The target experience is:

- clear section headings
- short overview first
- grouped items with consistent fields
- stable numbering
- explicit next steps
- cautious wording when evidence is limited
- no long unstructured paragraphs when the user asks for review, summary, comparison, or triage

This is mostly a **renderer and response-template improvement**, not a new agent capability.

---

## 2. Design Principle

Prefer deterministic backend renderers over free-form runtime agent prose for implemented fast paths.

For example, these functions should produce structured markdown directly:

- `_render_weekly_summary(...)`
- `_render_bug_review_summary(...)`
- `_render_resume_review_summary(...)`
- `_render_meeting_reservation_summary(...)`
- newsletter cleanup / unsubscribe response renderers
- daily summary card/history renderers where applicable

Prompt hints like "be structured" are useful, but they are not sufficient. The best UX improvement is to encode the output contract in the fast-path renderers.

---

## 3. Shared Response Template

Most inbox aggregation responses should follow this shape:

```text
Summary
I found X relevant items from [time window].

Top Items
1. Sender or title - short label
   Status: ...
   Date: ...
   Evidence: ...
   Next step: ...

2. Sender or title - short label
   Status: ...
   Date: ...
   Evidence: ...
   Next step: ...

Recommendation
- ...
```

Rules:

- Keep each item to 3-5 lines.
- Put the most important field first.
- Use `Evidence:` only for short snippets, not full email text.
- Use `Next step:` for what the user can do next.
- If the result is uncertain, say why in one line.
- Avoid repeating "You can ask me..." on every response unless it adds value.

---

## 4. Weekly Summary Format

Weekly or recent summary requests should not become a loose paragraph. Use a report-like structure.

Example:

```text
Weekly Summary
Period: Apr 3 - Apr 9

Overview
- 24 emails reviewed.
- 3 urgent/action-needed items.
- 2 follow-ups.
- Main topics: meetings, hiring, security, newsletters.

Priority Items
1. Sender - Subject
   Why it matters: ...
   Suggested action: ...

Follow-ups
1. Sender - Subject
   Needed from you: ...

Low Priority / FYI
- ...

Suggested Next Steps
- Reply to ...
- Review ...
- Ignore/archive ...
```

If data is limited:

```text
Weekly Summary
Period: Apr 3 - Apr 9

Overview
- I found X emails in the synced cache.
- No urgent follow-ups were detected.

Data Note
- Some details may be missing if Gmail sync has not completed.
```

Implementation note:

- Add or refine a weekly recap renderer rather than relying on the generic runtime response.
- Use counts from cache, triage, follow-up service, and topic classification where available.
- Keep item snippets under roughly 180-220 characters.

---

## 5. Meeting Review Format

Meeting review should clearly distinguish confirmed meetings from proposed meeting requests.

Example:

```text
Meeting Reservations
I found 4 upcoming meeting-related items.

Confirmed
1. Wenyu Ding - tomorrow 4:00 PM
   Subject: Reminder: Meeting Tomorrow at 4:00 PM
   Evidence: "meeting tomorrow at 4:00 pm"
   Next step: Already safe to add to calendar.

Proposed
2. Aiden_Yang - this Sunday 6:00 PM
   Subject: confirm a meeting
   Evidence: "meeting at this Sunday 6:00 pm"
   Next step: Confirm it or propose another time.

Ignored
- Older relative-date proposals were filtered out because their resolved dates are before today.
```

Rules:

- Do not call proposed meetings "booked" unless the user confirms.
- When the user says "confirm the meeting with Aiden on Sunday", write it to Calendar and say it was added.
- If multiple proposed meetings match the same person, use the day/time in the user message to disambiguate.

---

## 6. Resume Review Format

Resume review should separate attachment evidence from fit judgment.

Example:

```text
Resume Review
I found 2 candidate-related emails.

Candidates
1. zenglin zhong - AI / ML background
   Contact: zenglin0813@gmail.com
   Evidence: Resume_Jeremy_Academic.docx was extracted.
   Highlights: Computer vision, ML coursework, AI internship.
   Next step: Shortlist for an AI development screen.

2. Aiden_Yang - AI-related opportunity
   Contact: 945430408@qq.com
   Evidence: Resume attachment detected, but resume appears to be in Chinese.
   Limitation: English-language evaluation is limited.
   Next step: Ask for an English resume before comparing fit.

Recommendation
- zenglin is currently easier to evaluate from available English resume text.
```

Rules:

- Do not overclaim fit when attachment text is unavailable.
- If an attachment is detected but not extracted, say so.
- If the resume appears to be Chinese or otherwise non-English, suggest drafting a request for an English resume.
- When comparing candidates, distinguish "best available evidence" from "best candidate".

---

## 7. Bug Review Format

Bug review should be triage-oriented rather than a generic inbox recap.

Example:

```text
Bug Review
I found 3 technical issue emails that may need attention.

Priority Items
1. Build failure on main - P1
   Type: failing build
   Evidence: ...
   Next step: Check the CI failure and assign an owner.

2. Login regression report - P2
   Type: user-reported bug
   Evidence: ...
   Next step: Review the thread and confirm reproduction steps.

Recommendation
- Handle the build failure first because it blocks delivery.
```

Rules:

- Put severity/priority next to the title.
- Keep evidence short.
- Recommend the first action when confidence is high.
- If confidence is low, say "needs review" rather than assigning a hard priority.

---

## 8. Unsubscribe Format

Unsubscribe responses should avoid pivoting to unrelated senders when the user names a target.

Example:

```text
Subscription Cleanup
I found 3 recent mailing-list candidates.

Available
1. adidas - adidas@au-news.adidas.com
   Method: standard List-Unsubscribe
   Next step: Can queue unsubscribe after confirmation.

2. Flight Centre - deals@travel.flightcentre.com.au
   Status: already unsubscribed

Not Available
3. Nike - nike@notifications.nike.com
   Limitation: no standard unsubscribe link found in the synced data.
   Next step: Use Nike account/email preferences on the website, or try again after a future Nike email is synced.
```

Rules:

- If the user says "Nike only", do not suggest unsubscribing adidas as the primary next action.
- If a standard unsubscribe action is unavailable, explain the manual website path.
- Clearly distinguish "can queue", "queued", and "completed".

---

## 9. Frontend Rendering Considerations

The frontend currently uses a lightweight markdown renderer rather than a full markdown library.

Implications:

- Multi-line numbered list items can be split into multiple ordered lists.
- The renderer should preserve `ol start` when it sees an item beginning with `2.`, `3.`, etc.
- Long evidence snippets should be truncated by backend renderers before they reach the frontend.
- Avoid deeply nested lists because the renderer is intentionally simple.

Recommended frontend refinements:

- Preserve ordered list start numbers.
- Add spacing between major sections.
- Optionally add support for simple section headings without making the UI feel like a document viewer.

---

## 10. Implementation Order

### Step 1: Define Shared Formatter Helpers

Add small helpers in `EmailAgentClient` or a dedicated response formatting module:

- truncate evidence text
- format count/plural labels
- render section headers
- render item detail lines
- normalize empty fields

Done when:

- renderers use the same item shape and spacing rules.

### Step 2: Weekly Summary Renderer

Update weekly recap output first because it benefits most from structure.

Done when:

- weekly summary uses `Overview`, `Priority Items`, `Follow-ups`, and `Suggested Next Steps`.

### Step 3: Meeting Review Renderer

Group meeting items into:

- `Confirmed`
- `Proposed`
- `Ignored / filtered`

Done when:

- users can clearly tell which meetings are already booked vs which require confirmation.

### Step 4: Resume Review Renderer

Separate:

- candidate identity
- attachment evidence
- fit highlights
- limitation
- next step

Done when:

- candidate comparison reads like a concise screening note.

### Step 5: Bug Review and Unsubscribe Renderers

Apply the same structure to bug review and subscription cleanup.

Done when:

- each response has a consistent shape and action-oriented ending.

---

## 11. Testing Guidance

Add or update tests for:

1. weekly summary includes expected section names
2. meeting review groups confirmed and proposed items
3. resume review distinguishes extracted vs missing attachment text
4. bug review lists priority and next step
5. unsubscribe response does not pivot away from a named sender
6. frontend markdown renderer preserves ordered list numbering across split list blocks

Test style:

- Prefer asserting key lines and section headings rather than full long responses.
- Use fake service summaries where possible to keep tests deterministic.
- Keep frontend tests/type checks lightweight unless the project adds a dedicated UI test runner.

---

## 12. Definition of Done

This UX refinement is complete when:

- major fast-path responses use clear section headings
- lists are numbered correctly in chat
- evidence snippets are short and readable
- confirmed vs proposed states are explicit
- reply/action state is explicit for send/unsubscribe/calendar operations
- weekly summaries are report-like and not loose paragraphs
- tests cover representative output for each major workflow

