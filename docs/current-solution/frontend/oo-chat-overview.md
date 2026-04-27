# OO Chat Overview

## Role

`oo-chat/` is the web client for the current EmailAI solution. It is built with Next.js, React, Tailwind, and Zustand. It is not the email agent runtime; it communicates with the agent over HTTP.

## Main Areas

- `app/`: Next.js app router pages and API routes.
- `components/chat/`: chat messages, input, tool approval, and related UI components.
- `hooks/`: agent and chat helpers.
- `store/`: persisted frontend state such as sessions and agent addresses.
- `public/`: static assets.

## Modes

- Default-agent mode: the app opens directly into a chat backed by `DEFAULT_AGENT_URL` or `NEXT_PUBLIC_DEFAULT_AGENT_URL`.
- Address-book mode: users can add and switch between agent addresses.

## Session Model

The UI treats the conversation as a linear chat. The agent can still return structured trace or approval events, which the frontend renders as cards or controls.

## Build Commands

```bash
cd oo-chat
npm install
npm run dev
npm run build
```

In Docker deployments, the frontend is mapped to the configured external port, commonly `3300`.
