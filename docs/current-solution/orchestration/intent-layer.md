# Intent Layer

## Purpose

The intent layer is the first routing stage in `email-agent/intent_layer.py`. It decides whether a user turn can be answered directly or should enter the planner and execution pipeline.

## Core Decision

```python
DIRECT_RESPONSE_THRESHOLD = 9.0
should_direct_respond = confidence >= 9.0 and bool(final_response)
```

High-confidence conversational turns can be answered immediately. Lower-confidence or action-oriented turns proceed to planning.

## Outputs

The intent result can include:

- User-facing direct response.
- Classification and confidence.
- Execution trigger signal.
- Memory update notes.
- Reasoning hints for later stages.

## Memory Writeback

`user_update_summary` values are accumulated during the turn and later applied through `MarkdownMemoryStore` after finalization.

## Related Design Note

`intent-layer-plan.md` is the earlier design proposal. Runtime behavior is authoritative when the two differ.
