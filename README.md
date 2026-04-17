# 9900-H16C-Cake

## First Time

```bash
cp email-agent/.env.example email-agent/.env
```

Set `email-agent/.env`:

```bash
OPENAI_API_KEY=your_key
AGENT_MODEL=gpt-5.4
LINKED_GMAIL=true
LINKED_OUTLOOK=false
```

```bash
docker compose run --rm email-agent setup
docker compose up --build -d
```

Open [http://localhost:3300](http://localhost:3300)

## Start Again

```bash
docker compose up -d
```

## Stop

```bash
docker compose down
```
