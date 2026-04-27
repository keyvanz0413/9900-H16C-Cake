# Unsubscribe Overview

## Purpose

The unsubscribe subsystem lets the agent discover subscription senders and unsubscribe through safe automatic paths when possible.

## Layers

- Tool layer: parses unsubscribe headers and performs one-click POST when allowed.
- Workflow layer: groups messages into sender-level candidates.
- State layer: remembers candidates hidden after successful unsubscribe.
- Skill layer: exposes discovery and execution workflows to the planner.

## Safety Model

Discovery never unsubscribes. Execution requires a selected target and uses one-click or mailto only when available. Website unsubscribe paths are returned for manual action rather than automated browsing.

## User Flow

1. User asks what they can unsubscribe from.
2. Discovery returns candidates.
3. User selects targets.
4. Execution reports newly unsubscribed, already unsubscribed, manual action required, failed, and not found.
