# Orchestrator Flow

## Purpose

`IntentLayerOrchestrator` coordinates the current five-stage execution pipeline.

## Stages

1. Intent analysis: classify the user request and decide direct response versus execution.
2. Planning: build a serial plan with step dependencies.
3. Skill input resolution: turn natural language and prior artifacts into validated arguments.
4. Execution: run either a declared skill or a general main-agent step.
5. Finalization: produce the final user-facing answer and apply memory updates.

## Data Flow

Each step writes a structured result. Later steps can read prior outputs through planner `reads` declarations. The finalizer receives the collected execution trace.

## Failure Handling

A failed step should return a structured failure artifact. The finalizer explains the failure and avoids claiming unfinished work.

## Memory

Memory updates are collected during the turn and written only after the response path has enough context.
