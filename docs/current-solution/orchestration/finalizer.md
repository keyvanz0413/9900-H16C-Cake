# Finalizer

## Purpose

The finalizer is the only stage that produces the final user-facing answer. It receives structured step results and turns them into a concise response.

## Inputs

- Original user request.
- Planner steps and execution results.
- Skill bundles or main-agent artifacts.
- Memory update summaries when relevant.

## Responsibilities

- Explain completed work in user language.
- Preserve safety boundaries from skill bundles.
- Avoid claiming actions that did not complete.
- Ask for clarification only when execution cannot safely continue.
- Keep internal trace details out of the final answer unless useful.

## Prompt Location

The prompt is implemented in `email-agent/prompts/finalizer.md`.

## Output Expectations

The finalizer should respond from evidence in artifacts, not from assumptions. For draft-related skills it should clearly state that a draft is not sent unless a send step actually ran.
