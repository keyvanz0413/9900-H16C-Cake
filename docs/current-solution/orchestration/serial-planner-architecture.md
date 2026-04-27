# Serial Planner Architecture

## Purpose

This design note describes the serial planner used by the current solution. The planner decomposes user requests into ordered steps with explicit dependencies.

## Model

Each step has a goal, execution type, optional skill name, and optional reads from prior step artifacts. The executor runs steps in order and stores structured results.

## Why Serial

Serial execution is easier to reason about for email tasks because many operations depend on prior evidence: find a message, draft a reply, then optionally send it.

## Benefits

- Clear traceability.
- Stable handoff between skills and the main agent.
- Safer write operations because prerequisites are explicit.
- Easier finalization from collected artifacts.

## Limits

The planner is not a general DAG executor. Parallelism is intentionally avoided in the current design to reduce complexity.
