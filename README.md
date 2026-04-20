<div align="center">

# AI Email Agent

**An intent-driven, multi-agent email workspace.**
Read, search, triage, reply, unsubscribe — all with natural language.

[English](#english) · [中文](#中文)

</div>

---

<a id="english"></a>

## Overview

**Cake** is a capstone project (UNSW COMP9900 · Team H16C) that delivers an end-to-end AI email assistant. It pairs a Python multi-agent backend with a modern Next.js chat UI, and runs as a single Docker Compose stack.

Under the hood, Cake uses a **layered intent architecture** — a lightweight intent classifier routes requests to a planner, which picks and parameterizes **skills** (YAML-declared, Python-executed workflows). A main agent handles freeform tool use, while specialized writer agents maintain a persistent user profile, habits, and writing style.

## Features

- **Multi-Agent Intent Layer** — intent → planner → skill resolver → executor → finalizer
- **Gmail & Outlook** — switchable provider via a single env flag
- **Calendar Integration** — Google Calendar / Microsoft Calendar with approval flow
- **10+ Skills** — weekly summary, urgent triage, bug triage, resume review, draft reply, prepared send, unsubscribe discovery/execute, writing style profile, CRM init
- **Unsubscribe Workflow** — RFC 8058 one-click + mailto fallback, no browser automation
- **Persistent Memory** — `USER_PROFILE.md`, `USER_HABITS.md`, `WRITING_STYLE.md` auto-updated from activity
- **Modern Chat UI** — Next.js 16 + React 19 + Tailwind v4, streaming responses
- **One-Command Deploy** — `docker compose up` and go

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    User (Browser :3300)                     │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP
              ┌───────▼────────┐        ┌──────────────────┐
              │  oo-chat       │───────▶│   email-agent    │
              │  Next.js 16    │  :8000 │   FastAPI + LLM  │
              │  React 19      │        │                  │
              └────────────────┘        └────────┬─────────┘
                                                 │
                        ┌────────────────────────┼────────────────────┐
                        │                        │                    │
                   ┌────▼─────┐          ┌───────▼────────┐    ┌──────▼──────┐
                   │  Intent  │─────────▶│    Planner     │───▶│   Skills    │
                   │  Layer   │          │  (single-step) │    │  (YAML+PY)  │
                   └──────────┘          └────────────────┘    └──────┬──────┘
                                                                      │
                                         ┌────────────────────────────┤
                                         │                            │
                                  ┌──────▼──────┐              ┌──────▼──────┐
                                  │ Main Agent  │              │  Finalizer  │
                                  │ (ReAct+Tools)│             │  (writer)   │
                                  └──────┬──────┘              └─────────────┘
                                         │
         ┌───────────────┬───────────────┼───────────────┬───────────────┐
    ┌────▼────┐    ┌─────▼────┐    ┌─────▼────┐    ┌─────▼────┐    ┌─────▼────┐
    │  Gmail  │    │ Calendar │    │  Memory  │    │  Shell   │    │  TodoList│
    └─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

## 🚀 Quick Start

### Prerequisites

- [Docker](https://docs.docker.com/get-docker/) & Docker Compose
- An LLM API key (**one of**: OpenAI / Anthropic / Gemini / OpenOnion)
- A Gmail or Outlook account for OAuth

### 1 · Clone & Configure

```bash
cp email-agent/.env.example email-agent/.env
```

Edit `email-agent/.env`:

```env
# Pick one LLM provider
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=...
# GEMINI_API_KEY=...

AGENT_MODEL=gpt-5.4
INTENT_LAYER_MODEL=gpt-5.4
SKILL_SELECTOR_MODEL=gpt-5.4

# Pick one email provider
LINKED_GMAIL=true
LINKED_OUTLOOK=false
```

### 2 · Authenticate (first time only)

```bash
docker compose run --rm email-agent setup
```

This walks you through OpenOnion auth + Google OAuth and persists tokens to `email-agent/.env`.

### 3 · Launch

```bash
docker compose up --build -d
```

Open **http://localhost:3300** 🎉

### Everyday commands

```bash
docker compose up -d       # Start
docker compose down        # Stop
docker compose logs -f     # Tail logs
```

## Project Structure

```
9900-H16C-Cake/
├── docker-compose.yml              # Two-service stack
├── README.md                       # ← you are here
│
├── email-agent/                    # Python agent backend (port 8000)
│   ├── agent.py                    # Agent composition + tool wiring
│   ├── intent_layer.py             # Intent → Plan → Execute orchestrator
│   ├── unsubscribe_workflow.py     # Unsubscribe state machine
│   ├── unsubscribe_state.py        # Per-subscription state tracking
│   ├── cli.py / cli/               # Typer CLI + interactive REPL + host server
│   ├── prompts/                    # System prompts (one per agent role)
│   │   ├── main_agent_step.md
│   │   ├── intent_layer.md
│   │   ├── planner.md
│   │   ├── skill_input_resolver.md
│   │   ├── finalizer.md
│   │   └── ...
│   ├── skills/                     # Declarative skill workflows
│   │   ├── registry.yaml           # Skill contracts (input schema + scope)
│   │   ├── unsubscribe_discovery.py
│   │   ├── unsubscribe_execute.py
│   │   ├── urgent_email_triage.py
│   │   ├── bug_issue_triage.py
│   │   ├── resume_candidate_review.py
│   │   ├── weekly_email_summary.py
│   │   ├── draft_reply_from_email_context.py
│   │   ├── send_prepared_email.py
│   │   └── writing_style_profile.py
│   ├── tools/                      # Custom tools (attachments, unsubscribe)
│   ├── plugins/                    # ReAct plugins (gmail sync, calendar approval)
│   ├── data/                       # Local cache (contacts, emails, memory)
│   ├── tests/                      # pytest suite
│   ├── Dockerfile
│   ├── docker-entrypoint.sh        # Handles co init / auth / host boot
│   ├── requirements.txt
│   ├── USER_PROFILE.md             # Auto-maintained user context
│   ├── USER_HABITS.md              # Auto-maintained habits
│   └── WRITING_STYLE.md            # Auto-derived writing style
│
└── oo-chat/                        # Next.js 16 chat UI (port 3000 → 3300)
    ├── app/                        # App Router: page.tsx, api/chat/route.ts
    ├── components/chat/            # Chat component library
    ├── hooks/                      # useChat and friends
    ├── store/                      # Zustand state
    ├── public/                     # Static assets
    ├── package.json
    └── Dockerfile
```

## Configuration

### Core env vars (`email-agent/.env`)

| Variable | Description | Default |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | LLM provider key | — |
| `AGENT_MODEL` | Main execution model | `co/claude-sonnet-4-5` |
| `INTENT_LAYER_MODEL` | Intent classifier model | falls back to `AGENT_MODEL` |
| `PLANNER_MODEL` | Skill-planner model | falls back to `INTENT_LAYER_MODEL` |
| `FINALIZER_MODEL` | Finalizer model | falls back to `INTENT_LAYER_MODEL` |
| `LINKED_GMAIL` | Enable Gmail tools | `true` |
| `LINKED_OUTLOOK` | Enable Outlook tools | `false` |
| `AGENT_TIMEZONE` | Timezone for date tools | `Australia/Sydney` |
| `EMAIL_AGENT_TRUST` | Tool-approval policy (`strict`/`open`) | `open` (in compose) |

### Compose-level

| Variable | Description | Default |
|---|---|---|
| `OO_CHAT_PORT` | Host port for the chat UI | `3300` |

## 🧪 Development

### Run the backend without Docker

```bash
cd email-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python cli.py host --port 8000
```

### Run the UI without Docker

```bash
cd oo-chat
npm install --install-links
npm run dev   # http://localhost:3000
```

Point the UI at your backend by setting `DEFAULT_AGENT_URL=http://localhost:8000`.

### Tests

```bash
cd email-agent
pytest -q              # full suite
pytest -q tests/test_intent_layer.py   # single module
```

## 🗺️ Roadmap

- [x] Gmail + Outlook provider toggle
- [x] Intent-layer orchestrator
- [x] 10+ production skills
- [x] One-click + mailto unsubscribe

## 📜 License

Apache License 2.0 — see [`email-agent/LICENSE`](email-agent/LICENSE).

## 🙌 Acknowledgements

Built on top of [ConnectOnion](https://connectonion.com) — the Python agent framework powering the tool, memory, and plugin layers.

---

<a id="中文"></a>

## 项目概述

**Cake** 是新南威尔士大学 COMP9900 毕业设计项目（H16C 小组）。它是一个端到端的 AI 邮件助手：后端基于 Python 多智能体编排，前端使用 Next.js 构建的现代聊天界面，整体通过 Docker Compose 一键部署。

底层采用 **分层意图架构**：轻量意图分类器先识别用户请求，再由规划器选择并参数化 **技能（Skill）**（YAML 声明 + Python 执行）；主智能体处理自由式工具调用；专用写入智能体持续维护用户画像、习惯以及写作风格。

## 功能亮点

- **多智能体意图层** — 意图识别 → 规划 → 参数解析 → 执行 → 定稿
- **Gmail / Outlook 双栈** — 一个环境变量即可切换邮件提供商
- **日历集成** — Google / Microsoft 日历，事件创建前需用户批准
- **10+ 预置技能** — 周报、紧急邮件三分类、Bug 定位、简历审阅、回复草稿、定稿发送、退订发现与执行、写作风格画像、CRM 初始化
- **安全退订流程** — RFC 8058 一键退订 + mailto 兜底，不做浏览器自动化
- **持久化记忆** — 根据邮件活动自动维护 `USER_PROFILE.md` / `USER_HABITS.md` / `WRITING_STYLE.md`
- **现代聊天 UI** — Next.js 16 + React 19 + Tailwind v4，支持流式输出
- **开箱即用** — 一条 `docker compose up` 即可跑起来

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                 用户浏览器  (localhost:3300)                │
└─────────────────────┬───────────────────────────────────────┘
                      │ HTTP
              ┌───────▼────────┐        ┌──────────────────┐
              │   oo-chat UI   │───────▶│   email-agent    │
              │   Next.js 16   │  :8000 │   后端 + LLM     │
              └────────────────┘        └────────┬─────────┘
                                                 │
                        ┌────────────────────────┼────────────────────┐
                   ┌────▼─────┐          ┌───────▼────────┐    ┌──────▼──────┐
                   │ 意图层   │─────────▶│    规划器      │───▶│   技能层    │
                   └──────────┘          └────────────────┘    └──────┬──────┘
                                                                      │
                                  ┌──────▼──────┐              ┌──────▼──────┐
                                  │  主智能体   │              │   定稿器    │
                                  │ (ReAct+工具)│              └─────────────┘
                                  └──────┬──────┘
                                         │
         ┌───────────────┬───────────────┼───────────────┬───────────────┐
    ┌────▼────┐    ┌─────▼────┐    ┌─────▼────┐    ┌─────▼────┐    ┌─────▼────┐
    │  邮箱   │    │   日历   │    │   记忆   │    │   Shell  │    │  TodoList│
    └─────────┘    └──────────┘    └──────────┘    └──────────┘    └──────────┘
```

## 快速开始

### 环境要求

- [Docker](https://docs.docker.com/get-docker/) 及 Docker Compose
- LLM API 密钥（OpenAI / Anthropic / Gemini / OpenOnion 任选其一）
- 一个可用于 OAuth 的 Gmail 或 Outlook 账号

### 1 · 克隆与配置

```bash
git clone <repo-url> cake && cd cake
cp email-agent/.env.example email-agent/.env
```

编辑 `email-agent/.env`：

```env
# 选一个 LLM 提供商
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=...
# GEMINI_API_KEY=...

AGENT_MODEL=gpt-5.4
INTENT_LAYER_MODEL=gpt-5.4
SKILL_SELECTOR_MODEL=gpt-5.4

# 选一个邮件提供商
LINKED_GMAIL=true
LINKED_OUTLOOK=false
```

### 2 · 首次授权

```bash
docker compose run --rm email-agent setup
```

该命令会引导完成 OpenOnion 鉴权与 Google OAuth，并把 token 写回 `email-agent/.env`。

### 3 · 启动服务

```bash
docker compose up --build -d
```

浏览器打开 **http://localhost:3300** 🎉

### 常用命令

```bash
docker compose up -d       # 启动
docker compose down        # 停止
docker compose logs -f     # 实时日志
```

## 目录结构

```
9900-H16C-Cake/
├── docker-compose.yml              # 双服务编排
├── README.md                       # ← 当前文档
│
├── email-agent/                    # Python 智能体后端（端口 8000）
│   ├── agent.py                    # 智能体组合 / 工具装配入口
│   ├── intent_layer.py             # 意图→规划→执行 编排器
│   ├── unsubscribe_workflow.py     # 退订状态机
│   ├── unsubscribe_state.py        # 单订阅持久化状态
│   ├── cli.py / cli/               # Typer CLI + 交互式 REPL + host 服务
│   ├── prompts/                    # 各智能体角色的系统提示词
│   │   ├── main_agent_step.md
│   │   ├── intent_layer.md
│   │   ├── planner.md
│   │   ├── skill_input_resolver.md
│   │   └── finalizer.md
│   ├── skills/                     # 声明式技能工作流
│   │   ├── registry.yaml           # 技能契约（输入 schema + 作用域）
│   │   ├── unsubscribe_discovery.py
│   │   ├── unsubscribe_execute.py
│   │   ├── urgent_email_triage.py
│   │   ├── bug_issue_triage.py
│   │   ├── resume_candidate_review.py
│   │   ├── weekly_email_summary.py
│   │   ├── draft_reply_from_email_context.py
│   │   ├── send_prepared_email.py
│   │   └── writing_style_profile.py
│   ├── tools/                      # 自研工具（附件解析、退订等）
│   ├── plugins/                    # ReAct 插件（Gmail 同步、日历审批）
│   ├── data/                       # 本地缓存（联系人、邮件、记忆）
│   ├── tests/                      # pytest 测试集
│   ├── Dockerfile
│   ├── docker-entrypoint.sh        # 初始化 / 鉴权 / 启动入口
│   ├── requirements.txt
│   ├── USER_PROFILE.md             # 自动维护的用户画像
│   ├── USER_HABITS.md              # 自动维护的使用习惯
│   └── WRITING_STYLE.md            # 自动生成的写作风格
│
└── oo-chat/                        # Next.js 16 聊天前端（3000 → 3300）
    ├── app/                        # App Router：page.tsx / api/chat/route.ts
    ├── components/chat/            # 聊天组件库
    ├── hooks/                      # useChat 等自定义 Hook
    ├── store/                      # Zustand 状态管理
    ├── public/                     # 静态资源
    ├── package.json
    └── Dockerfile
```

## 配置说明

### 核心环境变量（`email-agent/.env`）

| 变量 | 说明 | 默认值 |
|---|---|---|
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | LLM 提供商密钥 | — |
| `AGENT_MODEL` | 主执行模型 | `co/claude-sonnet-4-5` |
| `INTENT_LAYER_MODEL` | 意图识别模型 | 回退至 `AGENT_MODEL` |
| `PLANNER_MODEL` | 规划器模型 | 回退至 `INTENT_LAYER_MODEL` |
| `FINALIZER_MODEL` | 定稿模型 | 回退至 `INTENT_LAYER_MODEL` |
| `LINKED_GMAIL` | 启用 Gmail 工具 | `true` |
| `LINKED_OUTLOOK` | 启用 Outlook 工具 | `false` |
| `AGENT_TIMEZONE` | 时区（用于日期工具） | `Australia/Sydney` |
| `EMAIL_AGENT_TRUST` | 工具授权策略（`strict`/`open`） | `open` |

### Compose 级

| 变量 | 说明 | 默认值 |
|---|---|---|
| `OO_CHAT_PORT` | 前端在宿主机暴露的端口 | `3300` |

## 本地开发

### 不使用 Docker 跑后端

```bash
cd email-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python cli.py host --port 8000
```

### 不使用 Docker 跑前端

```bash
cd oo-chat
npm install --install-links
npm run dev   # http://localhost:3000
```

设置 `DEFAULT_AGENT_URL=http://localhost:8000` 让前端连本地后端。

### 运行测试

```bash
cd email-agent
pytest -q                                # 全量
pytest -q tests/test_intent_layer.py     # 单模块
```

## 🗺️ 路线图

- [x] Gmail + Outlook 双栈切换
- [x] 意图层编排器
- [x] 10+ 生产级技能
- [x] 一键退订 + mailto 兜底

## 📜 许可证

Apache License 2.0 — 详见 [`email-agent/LICENSE`](email-agent/LICENSE)。

## 🙌 致谢

基于 [ConnectOnion](https://connectonion.com) 构建 —— 它为本项目提供了工具层、记忆层与插件机制。

---

<div align="center">
<sub>Made with by <b>UNSW COMP9900 Team H16C</b></sub>
</div>
