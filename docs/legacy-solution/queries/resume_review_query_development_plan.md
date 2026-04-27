# Resume Review Query Development Plan

## Current Status Update

Status: **implemented / strongly supported**.

The dedicated aggregation workflow described below has now been implemented. The current codebase includes `backend/app/services/review/resume_review_service.py`, an auto-selected `resume-review` skill, and an `EmailAgentClient` fast path that renders recent candidate/resume summaries. Remaining caveats mainly concern how much resume or attachment text is available in the inbox/cache data.

## 1. Feature Goal

### Pair
**Resume Review Query**

### Example User Inputs
- "Help me check what resumes have been received recently and analyse them."
- "Have we received any new candidate resumes?"
- "Summarise recent candidate emails."
- "Which applicants look strongest from recent resumes?"
- "Give me a quick review of recent hiring emails."

### Product Goal
This feature helps a founder or hiring decision-maker quickly understand:

- which candidate or resume-related emails arrived recently
- which ones likely include attached resumes, CVs, portfolios, or applicant details
- what each candidate's main profile looks like based on available email evidence
- which items deserve review, comparison, or follow-up
- what the likely next action is

This is **not** a full ATS or recruitment platform. It is an inbox-level resume intake and candidate review workflow.

The ideal result is a compact overview such as:

```text
I found 4 recent candidate-related emails.

1. Candidate A - backend/API background, resume attached, needs review.
2. Candidate B - frontend React portfolio, recruiter-forwarded, worth comparing.
3. Candidate C - full-stack profile, enough detail for a first pass.
4. Candidate D - data-oriented background, resume attached but sparse email context.

You can ask me to compare candidates, prepare a shortlist, or draft replies.
```

---

## 2. Key Design Decision

The main correction to the original plan is:

**Resume Review Query should be implemented primarily as a read-only inbox aggregation workflow, not as a single-thread workflow extension.**

Reason:

- The user asks "what resumes have been received recently", which requires scanning multiple recent messages and threads.
- `EmailWorkflowService` already has single-thread hiring brief support.
- Broad inbox requests do not currently run `resolve_thread_workflow`; they route through `read_only_inbox`.
- The existing `BugReviewService` and bug-review fast path are the closest architectural match.

Therefore, version 1 should add a dedicated aggregation service:

```text
backend/app/services/review/resume_review_service.py
```

And wire it like the existing bug-review flow:

- `AgentSkillSelector` detects explicit resume-review requests.
- `agent_skill_registry.py` exposes a `resume-review` skill for `read_only_inbox`.
- `EmailAgentClient._try_skill_fast_path(...)` calls `ResumeReviewService`.
- The service returns a structured summary that can be rendered directly.

Existing `hiring-briefing` should remain useful for a single candidate or recruiter thread, but it should not be the primary path for the broad resume-review query.

---

## 3. Current Codebase Basis

### Existing Strong Foundations

#### A. Aggregation Pattern Already Exists
Files:
- `backend/app/services/review/bug_review_service.py`
- `backend/app/services/agent/email_agent_client.py`
- `backend/app/services/agent/agent_skill_selector.py`
- `backend/app/services/agent/agent_skill_registry.py`

Current value:
- `BugReviewService` scans recent inbox cache and triage items.
- It dedupes candidates by thread.
- It ranks and returns a structured payload.
- `EmailAgentClient` has a skill fast path for `bug-review`.

This is the best pattern to reuse for resume review.

#### B. Existing Single-Thread Hiring Brief
Files:
- `backend/app/services/workflow/email_workflow_planner.py`
- `backend/app/services/workflow/email_workflow_service.py`
- `backend/app/services/agent/agent_skill_registry.py`

Current value:
- planner already supports `needs_hiring_brief`
- registry already contains `hiring-briefing`
- workflow service already builds `hiring_brief`
- hiring brief already reads thread context, attachment filenames, portfolio links, and body/attachment text when available

This should be reused or lightly enhanced, not rebuilt from scratch.

#### C. Email Triage Layer
Files:
- `backend/app/services/triage/email_triage_service.py`
- `backend/app/services/triage/email_triage_store.py`

Current value:
- triage already has a `hiring` category
- hiring keywords include resume/CV/application/candidate/recruiter/interview-related signals
- triage items already include priority, action requirement, suggested action, sender, subject, and thread id

This is enough for a first-pass candidate filter.

#### D. Gmail Cache and Attachment Metadata
Likely input fields:
- `subject`
- `from`
- `snippet`
- `body`
- `threadId`
- `internalDate`
- `attachmentFilenames`
- `attachmentTexts`
- `links`

Version 1 should use attachment filenames and available extracted text only. It should not require new OCR or PDF parsing.

---

## 4. Version 1 Scope

Version 1 should answer:

1. Which recent emails are candidate/resume related?
2. Which ones likely include resumes, CVs, portfolios, or cover letters?
3. What is a short, evidence-based summary of each candidate item?
4. What is the likely next action for each item?
5. Which items are strongest candidates for follow-up, using only lightweight signals?

Version 1 should not attempt:

- full ATS pipeline management
- interview scheduling automation
- OCR-heavy resume parsing
- deep HR scoring
- long-form resume extraction
- definitive candidate ranking when evidence is sparse

The output should be useful even when the email only says "please find attached my resume" and the attachment text is unavailable. In that case, mark the summary as limited instead of inventing details.

---

## 5. Proposed Architecture

## 5.1 Add `ResumeReviewService`

### New file
```text
backend/app/services/review/resume_review_service.py
```

### Recommended Shape
Use `BugReviewService` as the implementation template.

Core methods:

```python
class ResumeReviewService:
    def build_resume_review_summary(...): ...
    def list_resume_candidates(...): ...
    def rank_resume_candidates(...): ...
```

Suggested dataclass:

```python
@dataclass(frozen=True)
class ResumeReviewCandidate:
    thread_id: str
    message_id: str
    candidate_name: str
    candidate_email: str
    source_type: str
    role_hint: str
    has_resume_attachment: bool
    attachment_filenames: tuple[str, ...]
    profile_summary: str
    status: str
    next_step: str
    score: int
    reason_tags: tuple[str, ...]
    latest_sender: str
    latest_snippet: str
    received_at: str
```

### Why
Resume review is a multi-email aggregation problem. Keeping it in a dedicated service makes it:

- easier to test
- easier to fast-path
- less likely to conflict with single-thread workflow logic
- consistent with the current bug-review design

---

## 5.2 Candidate Detection Rules

### Strong Signals
Treat an email as a likely resume-review candidate when it has one or more strong signals:

- attachment filename contains `resume`, `cv`, `cover letter`, `cover_letter`, `portfolio`
- subject/snippet/body contains `job application`, `application for`, `applicant`, `candidate`, `resume`, `cv`, `cover letter`
- sender or text strongly suggests recruiter-forwarded candidate material
- triage category is `hiring` and suggested action is `prepare_hiring_overview`
- body includes applicant language such as "I am applying", "please find my resume", or "attached is my CV"

### Weak Signals
Use weak signals only as supporting evidence:

- `role`
- `position`
- `hiring`
- `interview`
- `career`
- `recruiting`

These can also appear in general hiring discussions, meeting coordination, job alerts, newsletters, or internal planning.

### False Positive Guard
Do not classify an item as a resume candidate from weak hiring language alone unless another signal is present.

For example:

- "Let's discuss hiring plans" should not be a resume candidate.
- "Interview availability for Candidate A" can be a hiring item, but may not be a resume item.
- "Please find attached my resume" is a strong resume candidate even if the body is short.

---

## 5.3 Attachment-Aware Detection

Version 1 should be lightweight:

1. read `attachmentFilenames`
2. detect resume-like filenames
3. optionally inspect `attachmentTexts` if already available
4. boost confidence when a resume/CV-like attachment is present
5. include attachment names as evidence in the result

Suggested attachment filename markers:

- `resume`
- `cv`
- `cover`
- `cover_letter`
- `portfolio`
- `work_sample`
- `.pdf`
- `.doc`
- `.docx`

Important: file extensions alone should not be enough. A PDF attachment is a boost only when combined with hiring/candidate context.

---

## 5.4 Candidate Brief Fields

For each candidate item, return:

- `thread_id`
- `message_id`
- `candidate_name`
- `candidate_email`
- `source_type`
- `role_hint`
- `has_resume_attachment`
- `attachment_filenames`
- `profile_summary`
- `status`
- `next_step`
- `reason_tags`
- `received_at`

Suggested `source_type` values:

- `direct_applicant`
- `recruiter_forwarded`
- `referral`
- `internal_hiring_thread`
- `unknown`

Suggested `status` values:

- `needs_review`
- `needs_comparison`
- `awaiting_reply`
- `not_enough_information`
- `likely_not_resume`

Suggested `next_step` values:

- `Review the resume attachment and decide whether to shortlist.`
- `Compare this candidate with other recent applicants.`
- `Request more information before evaluating fit.`
- `Read the full thread before replying.`
- `Ignore unless you are reviewing general hiring discussions.`

---

## 5.5 Summary Payload Contract

Return a frontend-friendly and testable shape:

```json
{
  "summary_title": "Recent candidate-related emails",
  "total_candidates": 4,
  "top_items": [
    {
      "thread_id": "abc123",
      "message_id": "msg123",
      "candidate_name": "Candidate A",
      "candidate_email": "candidate@example.com",
      "source_type": "direct_applicant",
      "role_hint": "backend engineer",
      "has_resume_attachment": true,
      "attachment_filenames": ["CandidateA_Resume.pdf"],
      "profile_summary": "Applied directly and attached a resume. Email mentions backend/API experience.",
      "status": "needs_review",
      "next_step": "Review the resume attachment and decide whether to shortlist.",
      "reason_tags": ["resume_attachment", "application_language"],
      "received_at": "2026-04-07T01:23:45+00:00"
    }
  ],
  "follow_up_options": [
    "compare candidates",
    "prepare shortlist",
    "open related thread",
    "draft a reply"
  ]
}
```

---

## 6. Skill and Routing Changes

## 6.1 Add `resume-review` Skill

### File
```text
backend/app/services/agent/agent_skill_registry.py
```

Add:

```python
"resume-review": AgentSkillSpec(
    name="resume-review",
    allowed_bundles=("read_only_inbox",),
    prompt_lines=(
        "Use the resume review workflow for this turn.",
        "Focus on recent candidate, application, resume, CV, portfolio, and recruiter-forwarded emails.",
        "Keep candidate summaries evidence-based and do not overclaim fit when details are sparse.",
    ),
    usage_hint_lines=(
        "Do not turn this into a generic hiring recap.",
        "Use attachment filenames as evidence, but do not claim to have read a resume unless attachment text is available.",
    ),
)
```

Keep `hiring-briefing` as the single-thread skill for `thread_deep_read`.

---

## 6.2 Extend Skill Selector

### File
```text
backend/app/services/agent/agent_skill_selector.py
```

Add a read-only inbox branch:

```python
elif self._looks_like_resume_review_request(normalized, raw_message):
    selected_spec = self._auto_select_spec("resume-review", bundle_name=bundle_name)
    reason = "explicit_resume_review_request"
```

Suggested request markers:

- `resume review`
- `recent resumes`
- `candidate resumes`
- `candidate emails`
- `applicant`
- `applicants`
- `cv`
- `cover letter`
- `portfolio`
- `job application`
- `which applicants`
- `hiring emails`

Avoid making `hiring` alone enough to trigger resume review.

---

## 6.3 Add Fast Path in Email Agent Client

### File
```text
backend/app/services/agent/email_agent_client.py
```

Add a service dependency:

```python
self._resume_review_service = ResumeReviewService(data_dir=self._paths.data_dir)
```

Extend `_try_skill_fast_path(...)`:

```python
if route_context.skill_name == "resume-review":
    self._emit_status("Reviewing recent candidate and resume emails")
    resume_review_reply = self._try_fast_resume_review_reply(message)
    if resume_review_reply is None:
        return None
    return route_context.skill_name, resume_review_reply
```

Add:

```python
def _try_fast_resume_review_reply(self, message: str) -> str | None:
    summary = self._resume_review_service.build_resume_review_summary(limit=5)
    return self._render_resume_review_summary(
        summary,
        language=self._preferred_response_language(message),
    ).strip()
```

Use `_render_bug_review_summary(...)` as the closest rendering model.

---

## 6.4 Optional: Lightly Enhance Single-Thread Hiring Brief

### File
```text
backend/app/services/workflow/email_workflow_service.py
```

The existing `_build_hiring_brief(...)` already handles:

- candidate/contact fields
- role hint
- attachment filenames
- portfolio links
- attachment text if already present
- pipeline stage
- next step

Only enhance it if necessary, for example:

- add `has_resume_attachment`
- add `resume_attachment_filenames`
- make "not enough information" explicit when attachment text is missing

Do not make this the core aggregation mechanism.

---

## 7. Implementation Order

### Step 1: Add Service
Files:
- `backend/app/services/review/resume_review_service.py`

Tasks:
- copy the broad structure of `BugReviewService`
- scan Gmail cache messages
- join triage items by message id
- detect candidate/resume signals
- dedupe by thread
- rank candidates
- return summary payload

Done when:
- service can return a stable structured summary without involving the runtime agent

### Step 2: Add Skill Routing
Files:
- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/agent/agent_skill_selector.py`

Tasks:
- add `resume-review` skill
- add explicit resume-review request detection
- keep it under `read_only_inbox`

Done when:
- "Help me check what resumes have been received recently" selects `resume-review`

### Step 3: Add Fast Path
Files:
- `backend/app/services/agent/email_agent_client.py`

Tasks:
- instantiate `ResumeReviewService`
- add `_try_fast_resume_review_reply`
- add `_render_resume_review_summary`
- add status label for `resume-review`

Done when:
- a resume-review request returns a direct structured response without relying on generic agent reasoning

### Step 4: Add Tests
Files:
- `backend/tests/test_resume_review_service.py`
- update `backend/tests/test_email_workflow_planner.py` or create selector-specific tests if needed
- update email agent client prompt/fast-path tests if the project has a suitable pattern

Minimum cases:

1. detects direct applicant email with resume attachment
2. detects recruiter-forwarded candidate profile
3. detects clear application email with no attachment
4. ignores unrelated newsletter
5. ignores weak internal hiring discussion with no candidate/resume evidence
6. treats `.pdf` as a boost only with hiring context
7. dedupes repeated messages in same thread
8. returns empty but safe summary when no candidates exist

### Step 5: Optional Single-Thread Enhancement
Files:
- `backend/app/services/workflow/email_workflow_service.py`

Tasks:
- add `has_resume_attachment` to hiring brief if useful
- add clearer prompt lines around limited evidence

Done when:
- thread-specific candidate questions get better evidence hints

---

## 8. Ranking Guidance

Suggested score factors:

- strong resume/CV attachment filename: high boost
- application language in subject/body: high boost
- triage category `hiring`: medium boost
- recruiter-forwarded candidate profile: medium boost
- portfolio/work sample link: medium boost
- action required or reply needed: medium boost
- recency: tie-breaker
- weak hiring-only signal: low boost
- newsletter/noise: strong penalty

Do not rank candidates as "best" based on sparse snippets alone. Prefer "most ready for review" or "strongest available signal" unless attachment text provides enough detail.

---

## 9. User-Facing Response Format

English example:

```text
I found 3 recent candidate-related emails.

1. Taylor Applicant - direct applicant, resume attached.
   Summary: Applied for a backend role and included a resume.
   Status: needs review.
   Next step: Review the resume attachment and decide whether to shortlist.

2. Jules Recruiter - recruiter-forwarded profile.
   Summary: Candidate profile appears to be forwarded by a recruiter.
   Status: needs comparison.
   Next step: Compare with other recent applicants.

3. Morgan Candidate - application email, no clear resume attachment found.
   Summary: The email looks candidate-related, but there is not enough resume evidence.
   Status: not enough information.
   Next step: Read the thread or request more details.

You can ask me to compare candidates, prepare a shortlist, or draft replies.
```

Chinese rendering can be added if the existing language detection path is used, but the internal contract should stay language-neutral.

---

## 10. Risks and Mitigations

### Risk 1: False positives on hiring chatter
Some emails mention hiring or roles but are not actual candidate submissions.

Mitigation:
- require a strong signal or multiple weak signals
- separate `hiring discussion` from `resume candidate`
- penalize newsletter/noise sources

### Risk 2: Weak candidate summaries
Many resume details may exist only in attachments.

Mitigation:
- use `not_enough_information`
- say "resume attached" instead of pretending to know the resume content
- only use attachment text when it is already available

### Risk 3: Overclaiming candidate fit
The system may rank candidates too aggressively.

Mitigation:
- rank by review readiness and evidence strength
- use cautious wording
- include reason tags and evidence fields

### Risk 4: Duplicate candidate items
The same candidate may appear across several messages in a thread.

Mitigation:
- dedupe by thread in version 1
- optionally dedupe by candidate email/name later when confidence is high

---

## 11. Definition of Done

Version 1 is complete when:

- a broad resume-review request selects `resume-review`
- the request runs through `read_only_inbox`, not thread-only workflow resolution
- recent candidate/resume emails are detected from inbox cache and triage data
- likely resume/CV attachments are recognized from filenames
- duplicate candidate threads are reduced
- each top item includes candidate/contact identity, source type, summary, status, next step, and evidence tags
- the response is concise and safe when information is sparse
- tests cover direct applicants, recruiter forwards, no-attachment applications, false positives, dedupe, and empty results

---

## 12. Recommended File Change List

### New file
- `backend/app/services/review/resume_review_service.py`

### Existing files to change
- `backend/app/services/agent/agent_skill_registry.py`
- `backend/app/services/agent/agent_skill_selector.py`
- `backend/app/services/agent/email_agent_client.py`
- `backend/app/services/workflow/email_workflow_service.py` only if single-thread hiring brief needs small evidence improvements

### Tests
- `backend/tests/test_resume_review_service.py`
- selector tests for `resume-review`
- email agent client fast-path test if practical

---

## 13. Short Developer Summary

Build Resume Review Query as a sibling of Bug Review Query:

1. add `ResumeReviewService` for inbox aggregation
2. add `resume-review` skill under `read_only_inbox`
3. detect explicit resume-review requests in `AgentSkillSelector`
4. add a fast path in `EmailAgentClient`
5. reuse existing hiring brief only for single-thread deep reads
6. keep attachment handling lightweight and evidence-based
7. test strong candidates, weak hiring chatter, duplicates, and empty inbox cases

This design fits the current architecture better than pushing the whole feature through `EmailWorkflowService`, because the pair is naturally a multi-email inbox scan rather than a single-thread brief.
