# Unsubscribe Tool Merge Plan

## Purpose

This design note records the decision to merge several small unsubscribe helper ideas into two LLM-facing tools.

## Final Tool Surface

- `get_unsubscribe_info`: inspect messages and return normalized unsubscribe metadata.
- `post_one_click_unsubscribe`: perform a compliant one-click POST request.

## Rationale

A smaller tool surface reduces LLM orchestration mistakes. The model should not manually stitch together header parsing, body parsing, mailto generation, and POST semantics when deterministic code can do it.

## Expected Benefits

- Fewer tool calls.
- Better safety boundaries.
- Easier finalizer instructions.
- Clearer testing surface.

## Relationship To Skills

Discovery uses metadata only. Execution uses metadata plus the one-click POST helper when the selected method is safe.
