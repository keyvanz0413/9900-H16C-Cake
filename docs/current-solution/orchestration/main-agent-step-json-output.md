# Main Agent Step JSON Output

## Purpose

This design note defines the structured output contract for a general main-agent step.

## Required Shape

```json
{
  "status": "success | partial | failed",
  "artifact": {
    "kind": "string",
    "summary": "string",
    "data": {}
  },
  "reason": "string"
}
```

## Rationale

Serial planning needs stable machine-readable artifacts. Later steps should be able to read fields from `artifact.data` instead of parsing free-form prose.

## Constraints

- Keep the JSON valid.
- Put user-facing explanation in the finalizer, not in raw step output.
- Use `partial` or `failed` when the step cannot fully achieve its goal.
- Do not hide tool failures inside a successful status.
