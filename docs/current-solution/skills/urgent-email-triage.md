# Urgent Email Triage Skill

## Purpose

`urgent_email_triage` searches recent inbox mail for urgent terms and returns a prioritized summary.

## Flow

1. Build a query for urgent terms within the selected day window.
2. Search matching emails.
3. Fetch relevant bodies when needed.
4. Return evidence and finalizer instructions.

## Priority Signals

The finalizer should prioritize deadlines, production blockers, direct requests, and sender importance. Promotional or automated messages should not be over-weighted solely because they contain urgent wording.

## Empty Results

If no urgent mail is found, state that clearly without inventing issues.
