# Agent Chain Fixes 2026-03-31

## Original Problems

1. `conversation_snapshot()` returned a shallow draft-session copy, so callers could mutate nested live state by accident.
2. Some heavy or state-changing tools were exposed in general bundles even though the related skills were still not active.
3. Turn rules were duplicated across router context, backend turn-policy text, and provider prompts, which increased drift risk.
4. Gmail and Outlook prompts repeated the same long instructions, so provider-specific maintenance required editing two near-identical files.

## Repair Plan

- Reuse the existing deep draft-session copier for snapshots instead of exposing shallow dict copies.
- Remove non-default meeting-write and CRM-bootstrap tools from the general agent bundles so the backend cannot access them by accident.
- Move shared turn semantics into one backend policy module and have context-building and turn-policy rendering read from the same source.
- Split prompts into one shared base prompt plus small Gmail/Outlook overlays that only keep provider-specific notes.

## Result

- `conversation_snapshot()` now returns a detached draft-session snapshot.
- `draft_reply` keeps drafting and meeting-suggestion tools, but no longer exposes meeting-write tools.
- `contact_or_crm` keeps contact maintenance tools, but no longer exposes `init_crm_database()` in normal chat turns.
- Shared turn rules now live in `backend/app/services/agent/agent_turn_policy.py`.
- Runtime prompts are now composed from `email_agent_base.md` plus a small provider overlay, reducing Gmail/Outlook duplication.

## Verification

- Updated backend tests for snapshot isolation and turn-policy behavior.
- Updated runtime and prompt tests for the tightened bundle boundaries and base-plus-overlay prompt structure.
