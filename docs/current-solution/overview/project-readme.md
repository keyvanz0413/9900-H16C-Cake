# AI Email Agent

AI Email Agent, also known as Cake, is an intent-driven multi-agent email workspace for reading, searching, triaging, replying, unsubscribing, and coordinating calendar actions through natural language.

## Features

- Intent -> planner -> skill resolver -> executor -> finalizer pipeline.
- Gmail and Outlook provider switching.
- Calendar integration with approval gates for write operations.
- YAML-declared Python skills for common email workflows.
- Markdown-backed user profile, habits, and writing style memory.
- Next.js chat UI through `oo-chat`.
- Docker Compose deployment.

## Quick Start

```bash
cp email-agent/.env.example email-agent/.env
docker compose run --rm email-agent setup
docker compose up --build -d
```

Open the frontend at the configured mapped port, commonly `http://localhost:3300`.

## Repository Map

- `email-agent/`: Python agent runtime, prompts, tools, skills, memory, and tests.
- `oo-chat/`: Next.js chat client.
- `docs/current-solution/`: documentation for the active architecture.
- `docs/legacy-solution/`: previous-generation documentation retained for traceability.
- `docs/requirements/`: project requirement material.

## License

Apache License 2.0. See `email-agent/LICENSE`.
