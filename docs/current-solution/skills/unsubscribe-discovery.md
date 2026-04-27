# Unsubscribe Discovery Skill

## Purpose

`unsubscribe_discovery` finds visible unsubscribe candidates from recent inbox mail without executing unsubscribe actions.

## Flow

1. Search recent inbox mail for likely subscription messages.
2. Fetch unsubscribe metadata with `get_unsubscribe_info`.
3. Group messages into sender-level candidates.
4. Hide candidates already marked as unsubscribed in local state.
5. Return a ranked list for user review.

## Candidate Data

A candidate includes sender identity, candidate id, available methods, representative subjects, evidence, and whether manual action may be required.

## Finalizer Expectations

Show a concise list of candidates and ask which ones to unsubscribe. Do not execute an unsubscribe action during discovery.
