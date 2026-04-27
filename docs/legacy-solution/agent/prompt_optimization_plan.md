# Email Agent prompt optimization plan

## 📊 Current state

### Existing prompt file layout
```
agents/email-agent/prompts/
├── email_agent_base.md    # Main agent system prompt
├── gmail_agent.md         # Gmail-specific config
├── outlook_agent.md       # Outlook-specific config
├── email_reviewer.md      # Email review sub-agent
├── style_profiler.md      # Style analysis sub-agent
├── weekly_summary_writer.md # Weekly summary sub-agent
└── crm_init.md            # CRM bootstrap sub-agent
```

### Strengths of the current design
1. **Modular split**: base prompt + provider-specific prompts
2. **Dynamic prompt assembly**: `_build_prompt()` injects context
3. **Context budget**: character budget controls exist
4. **Routing layer**: routes requests to different tool bundles

---

## ⚠️ Issues to improve

### 1. Unstable structured output
**Issue**: `email_reviewer.md` returns JSON without strict schema validation
```python
# Current shape
{
  "approved": true,
  "risk_level": "low",
  "issues": [],
  "boundary_flags": [],
  "suggested_reply": null,
  "review_summary": "Short summary"
}
```

**Risk**: the LLM may return malformed or incomplete JSON

### 2. Prompt structure could be clearer
**Issue**: section boundaries and priority are not explicit enough
- Current sections: `SYSTEM ROUTING`, `SYSTEM WORKFLOW`, `SYSTEM TOOL ACCESS`...
- But no explicit `[CRITICAL]`, `[IMPORTANT]`, `[CONTEXT]` priority ladder

### 3. Weak error-recovery guidance
**Issue**: when a tool call fails, the agent lacks a clear recovery playbook

### 4. Language instructions are scattered
**Issue**: language policy is split across multiple places instead of one section

---

## ✅ Proposed improvements

### 1. Stronger structured output schema

**Improve `email_reviewer.md`**:
```markdown
# Email Draft Reviewer

You review email drafts before they are shown or sent.

## Output Format

You MUST respond with ONLY a valid JSON object. No markdown fences, no extra text.

### Required Schema
\`\`\`json
{
  "approved": boolean,           // REQUIRED: true or false
  "risk_level": "low" | "medium" | "high",  // REQUIRED: exactly one
  "issues": string[],            // REQUIRED: empty array if none
  "boundary_flags": string[],    // REQUIRED: empty array if none
  "suggested_reply": string | null,  // REQUIRED: null if approved
  "review_summary": string       // REQUIRED: max 100 chars
}
\`\`\`

### Validation Rules
- If `approved` is false, `suggested_reply` MUST contain a revised draft
- If `risk_level` is "high", `issues` MUST have at least 1 item
- `review_summary` MUST be under 100 characters

### Example Output
\`\`\`json
{
  "approved": false,
  "risk_level": "medium",
  "issues": ["Contains placeholder [Your name]"],
  "boundary_flags": ["missing_signature"],
  "suggested_reply": "Subject: Re: Meeting\n\nHi Bob,\n\nLet's meet next Tuesday.\n\nBest,\nJohn",
  "review_summary": "Added proper signature, removed placeholder."
}
\`\`\`

## Review Criteria

### CRITICAL (auto-reject)
- Placeholder text like `[Your name]`, `[fill in]`, `A / B`
- Unsupported promises or commitments
- Mixed languages without explicit request
- Privacy/internal info leakage

### WARNING (review carefully)
- Tone mismatch with user request
- Missing signature when style profile exists
- Generic greeting when relationship context available

### OK (approve)
- Minor style adjustments that don't change meaning
- Minor length optimization
```

---

### 2. Main prompt structure

**Improve `email_agent_base.md`**:
```markdown
# Email Agent System Prompt

[CRITICAL INSTRUCTIONS]
These rules override all other instructions. Violations cause system failures.

## Identity
You are an email assistant that helps users manage their inbox through the EmailAI backend.

## Core Rules (NEVER VIOLATE)

### Output Rules
1. Return EXACTLY ONE language version unless user explicitly requests bilingual
2. NEVER include placeholders, slash options, or editor notes in drafts
3. NEVER claim actions completed before tool confirmation
4. End drafts with exactly ONE confirmation question

### Security Rules
1. NEVER expose credentials or API keys in responses
2. NEVER commit secrets or .env files
3. Ask confirmation before destructive actions

### Action Rules
1. Queue mailbox actions before claiming completion
2. Retrieve context (thread, memory) before conclusions
3. Use only tools available in current turn

---

[IMPORTANT BEHAVIOR]

## Operating Model

### Turn Types
The backend routes each request to exactly one turn type:
| Turn Type | Allowed Actions |
|-----------|-----------------|
| read_only_inbox | Search, read, summarize |
| thread_deep_read | Read full thread, provide briefing |
| draft_reply | Compose reply, apply style |
| mailbox_action | Queue archive/unsubscribe, confirm |
| contact_or_crm | Manage contacts, update CRM |

### Workflow
1. **Understand**: Parse user intent, identify turn type
2. **Retrieve**: Fetch relevant context (thread, memory, style)
3. **Act**: Execute appropriate tool(s)
4. **Verify**: Confirm action succeeded before claiming completion

---

[CONTEXT HANDLING]

## Language Policy

### Response Language
- Match the LANGUAGE of the current user message
- Preserve EMAIL CONTENT in its original language
- Localize only: greeting, closing, explanation

### Draft Language
- Match the THREAD's dominant language
- If thread is bilingual, match the LATEST message language
- User explicit request overrides above rules

### Examples
| User Message | Thread Language | Draft Language |
|--------------|-----------------|----------------|
| "Reply to Bob" | Chinese | Chinese |
| "Reply to this email" | English | Chinese (user request) |
| "Draft in English" | Chinese | English (user request) |

## Memory Context
When available, use:
- Current session goal
- Recent decisions
- User preferences (tone, style)
- Active projects

---

[TOOL USAGE]

## Available Tools This Turn
{tools will be injected here}

## Tool Access Rules
1. Use ONLY tools listed above
2. Do NOT mention tools not in the list
3. If tool fails, try alternative approach
4. Never guess tool parameters

## Retrieval Before Action
Before drafting or acting:
1. Search for relevant emails
2. Read thread context if replying
3. Load writing style profile
4. Check memory for preferences

---

[OUTPUT FORMAT]

## Draft Output Format
```
Subject: [subject line]

[body]

[closing phrase],
[signature name]

[confirmation question in draft language]
```

## Summary Output Format
- Start with key insight (1 sentence)
- Then details if needed
- Bullet points for multiple items

## Error Handling
If a tool fails:
1. Explain what failed (1 sentence)
2. Suggest alternative approach
3. Ask user for guidance if no alternative
```

---

### 3. Add Pydantic schema validation

**Add `backend/app/services/agent/agent_output_schemas.py`**:
```python
"""Structured output schemas for agent responses."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DraftReviewOutput(BaseModel):
    """Schema for email draft review output."""

    approved: bool = Field(description="Whether the draft is approved for sending")
    risk_level: RiskLevel = Field(description="Risk assessment level")
    issues: list[str] = Field(default_factory=list, description="List of issues found")
    boundary_flags: list[str] = Field(default_factory=list, description="Boundary violations")
    suggested_reply: str | None = Field(default=None, description="Revised draft if not approved")
    review_summary: str = Field(max_length=100, description="Brief summary of review")

    @field_validator("issues", "boundary_flags", mode="before")
    @classmethod
    def ensure_list(cls, v: Any) -> list[str]:
        if v is None:
            return []
        if isinstance(v, list):
            return [str(item) for item in v]
        return [str(v)]

    @field_validator("suggested_reply", mode="after")
    @classmethod
    def validate_suggested_reply(cls, v: str | None, info: Any) -> str | None:
        if not info.data.get("approved") and v is None:
            raise ValueError("suggested_reply is required when approved is False")
        return v


class DraftOutput(BaseModel):
    """Schema for draft email output."""

    subject: str = Field(min_length=1, max_length=200, description="Email subject line")
    body: str = Field(min_length=1, description="Email body content")
    closing: str = Field(description="Closing phrase (e.g., 'Best regards,')")
    signature: str = Field(description="Sender name")
    requires_confirmation: bool = Field(default=True)


class ActionQueueOutput(BaseModel):
    """Schema for queued action output."""

    action_type: str = Field(description="Type of action queued")
    target: str = Field(description="Target email or sender")
    status: str = Field(default="queued", description="Action status")
    requires_confirmation: bool = Field(default=True)
```

---

### 4. Prompt assembly improvements

**Change `email_agent_client.py`**:
```python
def _build_prompt(
    self,
    message: str,
    history: list[dict[str, str]],
    *,
    conversation_id: str | None = None,
    route_context: AgentRouteContext | None = None,
    brief_prompt_lines: tuple[str, ...] = (),
) -> str:
    """Build a structured prompt with clear sections."""
    
    sections: list[str] = []
    
    # 1. Critical Instructions (always first)
    sections.append(self._build_critical_section())
    
    # 2. Turn-specific context
    if route_context:
        sections.append(self._build_routing_section(route_context))
    
    # 3. Available tools
    sections.append(self._build_tools_section(route_context))
    
    # 4. Memory and context
    memory_context = build_memory_context(...)
    sections.append(self._build_memory_section(memory_context))
    
    # 5. History and current message
    sections.append(self._build_history_section(history, message))
    
    return "\n\n".join(sections)


def _build_critical_section(self) -> str:
    return """[CRITICAL - THESE RULES OVERRIDE ALL ELSE]

1. ONE language only unless bilingual explicitly requested
2. NO placeholders, slash options, or editor notes
3. NO claiming completion before tool confirms
4. END drafts with exactly one confirmation question"""
```

---

## 📋 Rollout plan

### Phase 1: Structured schemas (high priority) — done
- [x] Add `agent_output_schemas.py`
- [x] Update `email_reviewer.md` with strict schema
- [x] Add JSON validation
- [x] Add structured output schemas for workflows:
  - DraftReviewOutput
  - DraftEmailOutput
  - InboxSummaryOutput
  - WeeklySummaryOutput
  - MorningBriefOutput
  - ThreadBriefingOutput
  - EmailTriageOutput
  - ActionQueueOutput
  - MeetingSlotOutput
  - StyleProfileOutput
  - CRMContactOutput

### Phase 2: Prompt structure (medium priority) — done
- [x] Refactor `email_agent_base.md` with [CRITICAL]/[IMPORTANT] layers
- [x] Consolidate language policy into one section
- [x] Add error-recovery guidance
- [x] Add [STRUCTURED OUTPUTS] section

### Phase 3: Prompt file updates (medium priority) — done
- [x] Update `email_reviewer.md` — strict JSON schema
- [x] Update `weekly_summary_writer.md` — JSON structured output
- [x] Update `style_profiler.md` — JSON structured output
- [x] Update `crm_init.md` — JSON summary output
- [x] Add `inbox_summarizer.md` — JSON structured output
- [x] Add `thread_briefing.md` — JSON structured output

### Phase 4: Tests and validation (ongoing)
- [ ] Add schema validation tests
- [ ] Add multilingual output tests
- [ ] Add error-recovery tests

---

## 📦 Implemented structured output schemas

### Core schemas

| Schema | Purpose | Prompt file |
|--------|---------|-------------|
| `DraftReviewOutput` | Draft review | email_reviewer.md |
| `DraftEmailOutput` | Draft body | email_agent_base.md |
| `InboxSummaryOutput` | Inbox overview | inbox_summarizer.md |
| `WeeklySummaryOutput` | Weekly summary | weekly_summary_writer.md |
| `MorningBriefOutput` | Morning brief | (internal) |
| `ThreadBriefingOutput` | Thread analysis | thread_briefing.md |
| `EmailTriageOutput` | Triage | (internal) |
| `ActionQueueOutput` | Action queue | (internal) |
| `MeetingSlotOutput` | Meeting slots | (internal) |
| `StyleProfileOutput` | Writing style | style_profiler.md |
| `CRMContactOutput` | Contacts | crm_init.md |

### Schema examples

```python
# Inbox summary (for "summarize my inbox")
class InboxSummaryOutput(BaseModel):
    total_count: int
    unread_count: int
    urgent_count: int
    action_needed_count: int
    key_insight: str  # one-line takeaway
    top_topics: list[str]
    priority_items: list[InboxSummaryItem]
    suggested_actions: list[str]

# Weekly summary (for "summarize week's emails")
class WeeklySummaryOutput(BaseModel):
    start_date: str
    end_date: str
    total_emails: int
    sent_count: int
    received_count: int
    urgent_count: int
    action_needed_count: int
    reply_needed_count: int
    overview: str
    topic_breakdown: list[WeeklySummaryTopic]
    key_threads: list[str]
    follow_ups_needed: list[str]

# Thread analysis (specific thread)
class ThreadBriefingOutput(BaseModel):
    thread_id: str
    subject: str
    participants: list[str]
    message_count: int
    summary: str
    key_decisions: list[str]
    open_questions: list[str]
    action_items: list[str]
    message_timeline: list[ThreadMessageSummary]
    next_step: str | None
    reply_needed: bool
```

---

## 🔑 Key improvements

| Area | Before | After | Status |
|------|--------|-------|--------|
| Structured output | Unstable JSON | Pydantic + strict prompts | done |
| Prompt structure | Unclear section priority | [CRITICAL]/[IMPORTANT] labels | done |
| Error recovery | Weak | Fallback guidance | done |
| Multilingual | Scattered | Single Language Policy section | done |
| Task coverage | Mostly draft review | Structured outputs for major tasks | done |
