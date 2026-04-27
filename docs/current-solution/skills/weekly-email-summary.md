# Weekly Email Summary Skill

## Purpose

`weekly_email_summary` summarizes recent email activity for a configurable day window.

## Inputs

Typical arguments include a time window such as `days` and optional filters from the user request.

## Flow

1. Search recent inbox mail.
2. Group or summarize results by topic, sender, and action need.
3. Return a bundle for the finalizer.

## Finalizer Expectations

Produce a concise summary with important threads, action items, and low-priority noise separated when possible. Avoid over-claiming if the underlying search result is sparse.
