# Current Solution Documentation

This directory contains documentation for the active Cake / AI Email Agent solution. The files are grouped by topic rather than by where they used to live.

## Categories

- [Overview](overview/project-readme.md) - product overview, setup, and repository map.
- [Orchestration](orchestration/) - intent analysis, planning, skill input resolution, main-agent step execution, finalization, and memory writeback.
- [Skills](skills/) - YAML-declared Python skill workflows and their runtime contracts.
- [Providers](providers/) - Gmail, Outlook, calendar approval, attachment extraction, and provider switching.
- [Frontend](frontend/) - `oo-chat` structure, API route, and approval UI flow.
- [Deployment](deployment/) - Docker Compose and environment variables.
- [Memory](memory/) - Markdown-backed user memory and writing style files.
- [Unsubscribe](unsubscribe/) - discovery, one-click/mailto execution, state, and tool contracts.
- [Tools](tools/email-agent-tools.md) - email agent tool surface.
- [Queries](queries/email-agent-query-pairs.md) - query examples and prompt pairs.

## Authority

When a design note conflicts with an implementation note in this directory, prefer the implementation note. When any document conflicts with running code, prefer the code.
