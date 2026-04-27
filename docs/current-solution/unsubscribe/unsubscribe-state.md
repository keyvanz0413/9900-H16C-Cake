# Unsubscribe State

## Purpose

`email-agent/unsubscribe_state.py` stores local candidate lifecycle state so successfully handled subscriptions can be hidden from future discovery results.

## Default Path

The default state file is `email-agent/UNSUBSCRIBE_STATE.json` unless `UNSUBSCRIBE_STATE_PATH` overrides it.

## Main Statuses

- `active`: candidate can be shown in discovery.
- `hidden_locally_after_unsubscribe`: candidate was successfully handled and should be hidden.

## Write Rules

Only candidates with successful execution statuses should be hidden. Manual, failed, and not-found results should not be marked hidden.

## Deployment

Persist the state file in production. Otherwise discovery may show already handled subscriptions after a container rebuild.
