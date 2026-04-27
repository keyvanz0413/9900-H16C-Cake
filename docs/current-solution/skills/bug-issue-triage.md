# Bug Issue Triage Skill

## Purpose

`bug_issue_triage` searches recent inbox mail for bug, incident, build failure, test failure, and regression signals. It produces an engineer-friendly triage bundle.

## Flow

1. Build a Gmail query from bug-related terms and a day window.
2. Search matching emails.
3. Extract message ids from search results.
4. Fetch each email body.
5. Return raw evidence and finalizer instructions.

## Finalizer Expectations

Start with the count of bug-related emails found. Group results by priority: production/blocking issues, build or test failures, then other bug-related items. For each item, include source, subject, and a suggested action. Empty results should be reported plainly.
