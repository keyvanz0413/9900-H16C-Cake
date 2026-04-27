# Intent Layer Plan

## Purpose

This design note describes the move from a single prompt-driven agent to a layered intent architecture.

## Proposed Architecture

The request first passes through an intent stage. High-confidence conversational requests can receive a direct answer. Actionable requests move into a serial planner, then into skill input resolution, execution, and finalization.

## Skill Registry

Skills are declared in `email-agent/skills/registry.yaml`. The registry gives the planner a list of available workflows, gives the resolver input schemas, and gives the executor the allowed tool list for each skill.

## Key Decisions

- Use explicit thresholds for direct responses.
- Keep skill selection data-driven through YAML.
- Keep final user wording in a dedicated finalizer.
- Write durable user memory through Markdown writer agents.

## Current Status

The implementation documents in this directory are the source of truth for runtime behavior. This file remains as an architecture proposal and rationale.
