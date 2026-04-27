# Skill Input Resolver

## Purpose

The skill input resolver converts the user request, planner goal, and prior step artifacts into arguments that match the selected skill schema.

## Prompt Location

The prompt lives at `email-agent/prompts/skill_input_resolver.md`.

## Inputs

- User request.
- Planner step goal.
- Skill registry entry.
- `input_schema` and `resolver_guidance`.
- Results from dependencies listed in `reads`.

## Output

The resolver returns a JSON argument object. The executor validates it before calling `execute_skill`.

## Rules

- Do not invent required fields when evidence is missing.
- Use defaults from the skill schema when available.
- Prefer explicit user-provided values over inferred values.
- Preserve prior artifact values exactly when a step depends on them.
