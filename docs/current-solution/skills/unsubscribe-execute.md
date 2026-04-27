# Unsubscribe Execute Skill

## Purpose

`unsubscribe_execute` performs unsubscribe actions for selected candidates. It supports direct candidate ids and natural-language target queries.

## Inputs

- `candidate_ids`: ids returned by discovery.
- `target_queries`: sender names, domains, or natural-language descriptions.
- `method`: `auto`, `one_click`, `mailto`, or `website`.

At least one candidate id or target query is required.

## Target Resolution

The skill first checks visible local candidates and state records. If needed, it performs a targeted live search. Ambiguous multiple matches are treated as not found to avoid unsubscribing the wrong sender.

## Execution Methods

| Method | Behavior |
|---|---|
| `one_click` | POST through `post_one_click_unsubscribe`. |
| `mailto` | Submit or prepare a mailto unsubscribe request. |
| `website` | Do not automate; return the manual unsubscribe link. |
| `auto` | Choose the best available method. |

## State Updates

Successful candidates are marked `hidden_locally_after_unsubscribe` so discovery no longer shows them. Failed, manual, and not-found candidates do not change state.

## Finalizer Expectations

Report results under newly unsubscribed, already unsubscribed, manual action required, failed, and not found. Claim success only for candidates in the newly unsubscribed category.
