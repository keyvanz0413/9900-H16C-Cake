# Skill Finalizer Execution

## Purpose

This design note explains how declared skills hand evidence to the finalizer instead of writing final user responses themselves.

## Flow

1. Planner chooses a skill.
2. Resolver creates validated arguments.
3. Executor runs the skill with only the allowed tools.
4. Skill returns an evidence bundle.
5. Finalizer turns the bundle into the user-facing answer.

## Rationale

Separating execution from final wording keeps skills deterministic and keeps user communication consistent. It also reduces the chance that a skill claims work that a tool did not complete.

## Bundle Guidance

A useful bundle includes summary, evidence, caveats, and finalizer instructions. Write skills should include explicit action status.
