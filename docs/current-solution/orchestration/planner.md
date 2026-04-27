# Planner

## Purpose

The planner turns an executable user request into a serial plan. It chooses declared skills when a skill matches the goal, and falls back to a main-agent step for open-ended tool work.

## Prompt Location

The planner prompt lives at `email-agent/prompts/planner.md`.

## Plan Shape

A step usually includes:

- Step id.
- Goal.
- Step type, such as skill or main agent.
- Selected skill name when applicable.
- Read dependencies on earlier artifacts.

## Selection Rules

- Prefer a declared skill when the registry describes an exact workflow.
- Use main-agent steps for free-form tasks that need general tool reasoning.
- Keep plans serial and explicit; avoid hidden dependencies.

## Downstream Contract

Skill steps go through skill input resolution before execution. Main-agent steps must return the JSON artifact described in `main-agent-step.md`.
