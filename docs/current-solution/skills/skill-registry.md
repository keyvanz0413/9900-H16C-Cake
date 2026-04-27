# Skill Registry

## Purpose

All declared skills are registered in `email-agent/skills/registry.yaml`. The planner reads this registry to choose a skill, the resolver reads each `input_schema` to produce arguments, and the executor reads `used_tools` to inject only the allowed tools.

## Registry Fields

| Field | Purpose |
|---|---|
| `description` | Planner-facing description that affects selection. |
| `scope` | Read/write label used by UI and approval layers. |
| `used_tools` | Tool names that the skill may call. |
| `input_schema` | JSON schema-like contract for resolver output. |
| `resolver_guidance` | Extra guidance for converting natural language into arguments. |

## Skill Implementation Contract

Each `skills/<name>.py` module must export:

```python
def execute_skill(arguments, used_tools, skill_spec, skill_runtime=None, step_goal=None, read_results=None):
    ...
```

The function returns a dictionary with a `response` bundle, `completed` flag, and `reason` for logs.

## Bundle Pattern

Skill responses usually use bracketed sections such as `[SUMMARY]`, `[EVIDENCE]`, `[NOTES]`, and `[FINALIZER_INSTRUCTIONS]`. This gives the finalizer stable boundaries and keeps raw tool output separate from instructions.

## Adding A Skill

1. Implement `skills/my_skill.py` with `execute_skill`.
2. Add a top-level registry entry.
3. Provide clear resolver examples.
4. Add planner selection signals in `description`.
5. Run the backend agent tests.

New skills should not require planner or finalizer prompt changes when the registry entry is sufficient.

## Current Skills

- `weekly_email_summary`
- `urgent_email_triage`
- `bug_issue_triage`
- `resume_candidate_review`
- `draft_reply_from_email_context`
- `send_prepared_email`
- `writing_style_profile`
- `unsubscribe_discovery`
- `unsubscribe_execute`
