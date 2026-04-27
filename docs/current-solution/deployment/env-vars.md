# Environment Variables

## Purpose

This file summarizes the environment variables used by `email-agent` and `oo-chat` in the current solution. The concrete template should live in `email-agent/.env.example` when available.

## Model Configuration

- `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`: provider credentials. Configure at least one supported model provider.
- `AGENT_MODEL`: model used by the main agent.
- `INTENT_LAYER_MODEL`: model used by the intent classifier.
- `SKILL_SELECTOR_MODEL`: model used by planning and skill selection.

## Provider Selection

- `LINKED_GMAIL`: enables the Gmail branch when truthy.
- `LINKED_OUTLOOK`: enables the Outlook branch when truthy.

If both Gmail and Outlook are enabled, the current runtime prefers Gmail.

## Gmail And Outlook Credentials

Provider credentials and OAuth tokens are read from the agent environment. Gmail variables usually include Google OAuth client credentials and token values. Outlook variables usually include Microsoft OAuth client credentials and token values.

## Runtime State

- `UNSUBSCRIBE_STATE_PATH`: optional path for unsubscribe state JSON. Defaults to `email-agent/UNSUBSCRIBE_STATE.json`.
- `DEFAULT_AGENT_URL` / `NEXT_PUBLIC_DEFAULT_AGENT_URL`: frontend default agent endpoint.

## Persistence

Persist the following paths in container deployments:

- `email-agent/.co/`
- `email-agent/data/`
- `email-agent/USER_PROFILE.md`
- `email-agent/USER_HABITS.md`
- `email-agent/WRITING_STYLE.md`
- `UNSUBSCRIBE_STATE.json` when unsubscribe management is enabled.
