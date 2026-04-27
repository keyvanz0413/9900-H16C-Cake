# Main Agent Step

## Purpose

A main-agent step lets the general agent use tools freely for one planner step, then returns a structured JSON artifact for downstream steps and finalization.

## Contract

The step output should include:

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

## Field Meaning

| Field | Meaning |
|---|---|
| `status` | Whether the step achieved the planner goal. |
| `artifact.kind` | A free enum chosen for the concrete result. |
| `artifact.summary` | Human-readable summary for finalizer and later steps. |
| `artifact.data` | Structured values that later steps can read. |
| `reason` | Debug-oriented explanation. |

## Why JSON Is Required

Planner `reads` dependencies need stable addresses such as `artifact.data.to`. Free-form prose is too fragile for multi-step execution.
