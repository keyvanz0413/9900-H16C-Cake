# Legacy Solution Documentation Index

This directory keeps the previous-generation documentation by topic so architecture notes, workflow plans, and query-development documents remain traceable without mixing into the current solution docs.

## Architecture

- [`architecture/agent-capability-map.md`](architecture/agent-capability-map.md)
  Current agent capability map, tool bundles, and provider/runtime boundaries.
- [`architecture/architecture-diagram.md`](architecture/architecture-diagram.md)
  High-level system architecture, data boundaries, and major flows.
- [`architecture/frontend-backend-agent-security-plan.md`](architecture/frontend-backend-agent-security-plan.md)
  Frontend, backend, and embedded-agent security boundaries.
- [`architecture/data-directory-refactor-plan.md`](architecture/data-directory-refactor-plan.md)
  Data layout refactor and storage structure plan.
- [`architecture/unified-data-workflow-refactor-plan.md`](architecture/unified-data-workflow-refactor-plan.md)
  Unified data and workflow refactor notes.

## Agent

- [`agent/prompt_optimization_plan.md`](agent/prompt_optimization_plan.md)
  Prompt structure and output-contract optimization plan.
- [`agent/agent_response_structure_improvement_plan.md`](agent/agent_response_structure_improvement_plan.md)
  Agent response structure improvement notes.
- [`agent/agent-chain-fixes-2026-03-31.md`](agent/agent-chain-fixes-2026-03-31.md)
  Agent chain fix log and follow-up notes.
- [`agent/email_agent_pairs_combined.md`](agent/email_agent_pairs_combined.md)
  Combined notes for agent prompt and pair design.

## Workflow

- [`workflow/email_initialization_pipeline.md`](workflow/email_initialization_pipeline.md)
  Email initialization, sync, triage, and briefing pipeline walkthrough.
- [`workflow/email-priority-funnel-plan.md`](workflow/email-priority-funnel-plan.md)
  Unified triage funnel and prioritization flow.
- [`workflow/personalized-email-workflow-plan.md`](workflow/personalized-email-workflow-plan.md)
  Personalized email workflow design and implementation plan.
- [`workflow/email-agent-secretary-memory-plan.md`](workflow/email-agent-secretary-memory-plan.md)
  Secretary-style agent and memory-layer design.
- [`workflow/follow-up-service-plan.md`](workflow/follow-up-service-plan.md)
  Follow-up service design notes.
- [`workflow/email_pipeline_analysis.py`](workflow/email_pipeline_analysis.py)
  Script-form documentation for email pipeline analysis.

## Gmail

- [`gmail/gmail-agent-refactor-plan.md`](gmail/gmail-agent-refactor-plan.md)
  Gmail + agent runtime refactor notes.
- [`gmail/gmail-sync-and-push-plan.md`](gmail/gmail-sync-and-push-plan.md)
  Gmail sync, watch, and push webhook design.
- [`gmail/gmail-unsubscribe-plan.md`](gmail/gmail-unsubscribe-plan.md)
  Newsletter and unsubscribe handling boundaries.

## Operations

- [`operations/contribution_rules.md`](operations/contribution_rules.md)
  Repository development and submission rules.
- [`operations/pipeline-visibility-observability-checklist.md`](operations/pipeline-visibility-observability-checklist.md)
  Visibility and observability checklist.
- [`operations/pipeline_quick_reference.md`](operations/pipeline_quick_reference.md)
  Quick operational reference.

## Query Development

- [`queries/bug_review_query_development_plan.md`](queries/bug_review_query_development_plan.md)
  Bug review query-development plan.
- [`queries/resume_review_query_development_plan.md`](queries/resume_review_query_development_plan.md)
  Resume review query-development plan.
- [`queries/important_contact_followup_query_development_plan.md`](queries/important_contact_followup_query_development_plan.md)
  Important-contact follow-up query-development plan.
- [`queries/draft_reply_strategy_query_development_plan.md`](queries/draft_reply_strategy_query_development_plan.md)
  Draft-reply strategy query-development plan.

## Other

- [`gpt-actions/openapi.yaml`](gpt-actions/openapi.yaml)
  OpenAPI contract for GPT Actions integration.
- [`archive/README.md`](archive/README.md)
  Historical or superseded design notes.
