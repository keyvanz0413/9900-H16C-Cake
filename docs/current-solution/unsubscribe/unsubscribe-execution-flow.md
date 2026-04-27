# Unsubscribe Execution Flow

## Purpose

This design note describes how selected unsubscribe targets move from user intent to safe execution.

## Flow

1. Resolve selected candidates from ids or target queries.
2. Refresh unsubscribe metadata for each candidate.
3. Choose the effective method: one-click, mailto, website, or failure.
4. Execute only safe automatic methods.
5. Mark successful candidates hidden in local state.
6. Return categorized results for finalization.

## Safety Rules

- Do not execute website unsubscribe flows automatically.
- Treat ambiguous target matches as not found.
- Claim success only when a tool reports a successful unsubscribe request.
- Preserve manual links for user action.
