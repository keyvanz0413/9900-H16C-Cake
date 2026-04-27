# Docker Compose Deployment

## Purpose

The Docker Compose setup runs the current solution as two cooperating services: the Python `email-agent` runtime and the Next.js `oo-chat` client.

## Services

- `email-agent`: Python agent runtime, FastAPI/ConnectOnion host, email tools, memory files, skills, and provider integrations.
- `oo-chat`: Next.js chat UI that connects to the agent through HTTP and the configured agent URL.

## Expected Mounts

The agent container needs persistent access to:

- `email-agent/.env` for provider keys and OAuth tokens.
- `email-agent/.co/` for ConnectOnion identity and session state.
- `email-agent/data/` for local runtime state and caches.
- `email-agent/USER_PROFILE.md`, `USER_HABITS.md`, and `WRITING_STYLE.md` for Markdown memory.

## Startup Flow

1. Build both containers.
2. Start `email-agent` and load environment variables.
3. Initialize ConnectOnion state if needed.
4. Start `oo-chat` and point it at the default agent URL.
5. Use the browser UI on the mapped frontend port.

## Common Commands

```bash
docker compose up --build -d
docker compose logs -f
docker compose down
```

## Notes

`UNSUBSCRIBE_STATE.json` defaults to the `email-agent/` directory unless `UNSUBSCRIBE_STATE_PATH` redirects it. Production deployments should mount it or place it under a mounted data directory.
