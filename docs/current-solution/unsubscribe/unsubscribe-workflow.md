# Unsubscribe Workflow

## Purpose

`email-agent/unsubscribe_workflow.py` contains shared pure workflow logic used by `unsubscribe_discovery` and `unsubscribe_execute`.

## Responsibilities

- Build subscription-oriented mailbox queries.
- Normalize sender and domain information.
- Group email-level unsubscribe metadata into sender-level candidates.
- Match user target queries to visible candidates.
- Build targeted search queries for execution.
- Prepare categorized result data for skills.

## Why It Is Separate

The workflow logic does not depend on ConnectOnion or LLM calls. Keeping it separate makes discovery and execution easier to test and keeps skill files focused on orchestration.

## Candidate Matching

Matching should prefer exact candidate ids, sender names, domains, and representative subjects. Ambiguous matches should not trigger automatic unsubscribe.
