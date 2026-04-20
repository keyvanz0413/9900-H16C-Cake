<div align="center">

# 🎂 Cake — AI Email Agent

**An intent-driven, multi-agent email workspace.**
Read, search, triage, reply, unsubscribe — all with natural language.

[![Python](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/)
[![Next.js](https://img.shields.io/badge/Next.js-16-black.svg)](https://nextjs.org/)
[![React](https://img.shields.io/badge/React-19-61dafb.svg)](https://react.dev/)
[![Docker](https://img.shields.io/badge/docker-compose-2496ed.svg)](https://docs.docker.com/compose/)
[![License](https://img.shields.io/badge/license-Apache%202.0-green.svg)](email-agent/LICENSE)
[![UNSW COMP9900](https://img.shields.io/badge/UNSW-COMP9900--H16C-ffcd00.svg)](#)

[English](#english) · [中文](#中文)

</div>

---

<a id="english"></a>

## 📖 Overview

**Cake** is a capstone project (UNSW COMP9900 · Team H16C) that delivers an end-to-end AI email assistant. It pairs a Python multi-agent backend with a modern Next.js chat UI, and runs as a single Docker Compose stack.

Under the hood, Cake uses a **layered intent architecture** — a lightweight intent classifier routes requests to a planner, which picks and parameterizes **skills** (YAML-declared, Python-executed workflows). A main agent handles freeform tool use, while specialized writer agents maintain a persistent user profile, habits, and writing style.

## ✨ Features

- 🧠 **Multi-Agent Intent Layer** — intent → planner → skill resolver → executor → finalizer
- 📬 **Gmail & Outlook** — switchable provider via a single env flag
- 🗓️ **Calendar Integration** — Google Calendar / Microsoft Calendar with approval flow
- 🛠️ **10+ Skills** — weekly summary, urgent triage, bug triage, resume review, draft reply, prepared send, unsubscribe discovery/execute, writing style profile, CRM init
- ✂️ **Unsubscribe Workflow** — RFC 8058 one-click + mailto fallback, no browser automation
- 📝 **Persistent Memory** — `USER_PROFILE.md`, `USER_HABITS.md`, `WRITING_STYLE.md` auto-updated from activity
- 💬 **Modern Chat UI** — Next.js 16 + React 19 + Tailwind v4, streaming responses
- 🐳 **One-Command Deploy** — `docker compose up` and go

## 🔬 Technical Highlights

Cake isn't just "LLM + Gmail API". Below are the design decisions that make the system **controllable, debuggable, and extensible** — each paired with a real user scenario.

### ① Serial Planner — decouple *what to do* from *how to do it*

Most agents let one big LLM both plan and execute, which makes behavior hard to reproduce. Cake splits the pipeline into five single-purpose LLM roles, each with a **strict JSON contract**:

```
Intent Layer  →  Planner  →  Skill Input Resolver  →  Executor  →  Finalizer
 (what user    (ordered     (fills args for ONE      (runs skill  (one pass,
  wants)        steps)       skill, no context)       or agent)    unified voice)
```

- **Planner** emits an ordered `steps[]` array. Each step is either `type: skill` or `type: agent`, and declares `reads: [step_ids]` so the runtime — not the model — decides which prior results get passed in.
- **No step has two jobs.** The planner never fills skill arguments; the resolver never decides which skill to run; skills never speak to the user. Fewer responsibilities per LLM call ⇒ less drift, easier evals.

> **Scenario — "summarize this week and send the summary to my boss"**
> Planner outputs two steps: `step_1: skill/weekly_email_summary` → `step_2: skill/send_prepared_email` with `reads: ["step_1"]`. The runtime hands `step_1`'s artifact to step 2's resolver, the summary gets inlined as the email body, and the finalizer speaks once at the end. No step is ever asked to "do two things at once."

### ② Skill Input Resolver — small input surface, zero drift

Each skill step is preceded by a **dedicated micro-LLM** whose only job is to fill `skill_arguments`. Its input is intentionally narrow:

- ✅ `intent`, current step `goal`, skill `input_schema`, only the `reads`-specified prior results
- ❌ no full conversation, no other skills, no tool catalog

Because the resolver can't see the rest of the world, it physically can't hallucinate a step change or a different skill. Arguments are then **validated against the declared `input_schema`** before the skill runs.

### ③ Declarative Skill Contracts (YAML)

Every skill is registered in [`email-agent/skills/registry.yaml`](email-agent/skills/registry.yaml) with four fields that make capability visible to the planner **without reading Python**:

```yaml
- name: unsubscribe_execute
  description: Execute unsubscribe for one or more explicit targets.
  scope: Supports RFC 8058 one-click POST and mailto. Never opens websites,
         never archives, deletes, or labels messages.
  used_tools: [search_emails, get_unsubscribe_info, post_one_click_unsubscribe, send]
  input_schema: { target_queries: list(required), candidate_ids: list, ... }
```

The `scope` field is a **hard behavior boundary** surfaced in the planner prompt — adding a new skill is a YAML edit + one Python file, no framework changes.

### ④ Unified Finalizer — one voice, one pass

Instead of wrapping each skill's output for the user, the finalizer runs **exactly once** at the tail of every request, reading `intent + older_context + recent_context + all step_results`. This fixes two real problems:

- **Style consistency**: skills emit structured artifacts, not prose — so "weekly summary" and "unsubscribe report" sound like the same assistant.
- **Cross-step synthesis**: when the user runs multiple skills in one turn, the finalizer can reference all of them together ("I summarized your week *and* sent it to Sarah").

### ⑤ Unsubscribe State Machine — "search finds, state decides"

The unsubscribe flow is the clearest example of **stateful AI**. A naïve agent would re-search Gmail and re-show already-unsubscribed senders. Cake separates discovery from display:

```
Every query  →  live Gmail search  →  candidate aggregation
             →  merge into local state file (never deletes)
             →  filter out status = hidden_locally_after_unsubscribe
             →  return the "visible" view only
```

Execution supports **multi-target** inputs (`"unsubscribe JB Hi-Fi and Louis Vuitton"`), prefers candidates from the current list, and falls back to a **targeted re-discovery** per unresolved target — rather than refusing. Responses always split results into *newly unsubscribed / already unsubscribed / not located / manual action required* so the user is never lied to about success.

> **Scenario — user says *"unsubscribe Qudos Bank, JB Hi-Fi, and Louis Vuitton"***
> The resolver pulls all three `target_queries`. Qudos Bank matches the current list → one-click POST. JB Hi-Fi was already hidden locally → reported as *already unsubscribed*, not re-executed. Louis Vuitton isn't in the list → runtime spins a targeted search, aggregates a fresh candidate, executes mailto, updates local state. The finalizer returns one clear 3-bucket summary.

### ⑥ Agent Step as Structured JSON

When the planner drops in a `type: agent` step, the main agent **does not speak directly to the user**. It emits:

```json
{ "status": "completed", "artifact": { "kind": "agent_result", "summary": "...", "data": {} }, "reason": "..." }
```

This makes skill steps and agent steps **uniform middle results** — the finalizer sees a single stream of artifacts and doesn't care which LLM produced each one.

### ⑦ Context Window Discipline

The Intent Layer receives a hard-split context: `older_context` (≤40 items) + `recent_context` (≤10 items), explicitly tagged. Tool traces are never injected — they're compressed to natural-language summaries first. Recent turns get higher weight by prompt construction, not by truncation, so short follow-ups like *"yes, that one"* are resolved without pulling a 200-message scrollback into every call.

### ⑧ Self-Maintaining User Memory

Three Markdown files — `USER_PROFILE.md`, `USER_HABITS.md`, `WRITING_STYLE.md` — are written by **dedicated writer agents** after each session. The writing-style profile is derived from your own sent emails via the `writing_style_profile` skill, so drafted replies match *your* voice (not a generic AI tone) — and you can read/edit the files directly, they aren't hidden in a DB.

### ⑨ Calendar Approval Plugin

Meeting creation uses a **ReAct plugin** that pauses before any mutating calendar call and surfaces a preview to the user. The LLM never sees "calendar successfully booked" until the user confirms — preventing a class of silent-side-effect bugs common in agentic systems.

### ⑩ Provider-Agnostic Email Backend

`LINKED_GMAIL` / `LINKED_OUTLOOK` are the only switches needed to swap providers. Tool instances are assembled at boot based on env flags, and a compatibility mixin normalizes OpenAI-style tool schemas across SDK differences. Same skill layer, two mailboxes.

## 🏗️ Architecture

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
git clone <repo-url> cake && cd cake
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

## 🧩 Project Structure

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

## ⚙️ Configuration

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

## 📖 项目概述

**Cake** 是新南威尔士大学 COMP9900 毕业设计项目（H16C 小组）。它是一个端到端的 AI 邮件助手：后端基于 Python 多智能体编排，前端使用 Next.js 构建的现代聊天界面，整体通过 Docker Compose 一键部署。

底层采用 **分层意图架构**：轻量意图分类器先识别用户请求，再由规划器选择并参数化 **技能（Skill）**（YAML 声明 + Python 执行）；主智能体处理自由式工具调用；专用写入智能体持续维护用户画像、习惯以及写作风格。

## ✨ 功能亮点

- 🧠 **多智能体意图层** — 意图识别 → 规划 → 参数解析 → 执行 → 定稿
- 📬 **Gmail / Outlook 双栈** — 一个环境变量即可切换邮件提供商
- 🗓️ **日历集成** — Google / Microsoft 日历，事件创建前需用户批准
- 🛠️ **10+ 预置技能** — 周报、紧急邮件三分类、Bug 定位、简历审阅、回复草稿、定稿发送、退订发现与执行、写作风格画像、CRM 初始化
- ✂️ **安全退订流程** — RFC 8058 一键退订 + mailto 兜底，不做浏览器自动化
- 📝 **持久化记忆** — 根据邮件活动自动维护 `USER_PROFILE.md` / `USER_HABITS.md` / `WRITING_STYLE.md`
- 💬 **现代聊天 UI** — Next.js 16 + React 19 + Tailwind v4，支持流式输出
- 🐳 **开箱即用** — 一条 `docker compose up` 即可跑起来

## 🔬 技术亮点

Cake 并不是简单的「LLM + Gmail API」。下列每一条设计都为了让系统 **可控、可调试、可扩展**，并配有一个实际场景。

### ① 串行 Planner —— 把「做什么」和「怎么做」彻底拆开

大多数 agent 让一颗大 LLM 同时决定规划和执行，行为不可复现。Cake 把整条链路拆成 5 个单职 LLM 角色，每一个都有 **严格 JSON 契约**：

```
意图层  →  规划器  →  技能参数解析器  →  执行器  →  定稿器
(用户   (有序的   (只给一个 skill      (跑 skill   (只一次，
 意图)   steps)    填参数，无上下文)    或 agent)    统一口吻)
```

- **Planner** 输出有序的 `steps[]`，每一步要么是 `type: skill`，要么是 `type: agent`，并通过 `reads: [step_ids]` 声明依赖 —— 由 runtime（而不是模型）负责按需把前序结果注入。
- **每个角色只做一件事**：Planner 不填技能参数，Resolver 不选技能，Skill 不直接对用户讲话。职责越窄 ⇒ 漂移越小，越容易做评测。

> **场景 —— "帮我总结这周邮件，然后把总结发给老板"**
> Planner 输出两步：`step_1: skill/weekly_email_summary` → `step_2: skill/send_prepared_email`，其中 `reads: ["step_1"]`。Runtime 把 `step_1` 的 artifact 传给 step 2 的 resolver，周报自动成为邮件正文，最后由 finalizer 统一开口。没有任何一步被要求"一次做两件事"。

### ② 技能参数解析器 —— 输入越小，越不飘

每个 skill step 前面都有一个 **专属微型 LLM**，唯一职责是填 `skill_arguments`。它的输入被刻意裁剪：

- ✅ `intent`、当前 step 的 `goal`、当前 skill 的 `input_schema`、仅 `reads` 指定的前序结果
- ❌ 不给完整对话、不给其他 skill 列表、不给工具目录

因为看不到全局，它**物理上无法**擅自改流程或换 skill。生成的参数还会在执行前用 `input_schema` **做一次后端校验**。

### ③ 声明式技能契约 (YAML)

所有技能都注册在 [`email-agent/skills/registry.yaml`](email-agent/skills/registry.yaml)，用四个字段把"能力边界"暴露给 planner —— **不用读 Python 也能理解能力**：

```yaml
- name: unsubscribe_execute
  description: 对一个或多个明确目标执行退订。
  scope: 仅支持 RFC 8058 一键 POST 与 mailto；绝不打开网页，
         绝不归档、删除或打标签。
  used_tools: [search_emails, get_unsubscribe_info, post_one_click_unsubscribe, send]
  input_schema: { target_queries: list(required), candidate_ids: list, ... }
```

`scope` 字段是一条**硬边界**，会直接出现在 planner 的 prompt 里。新增一个技能只需要改 YAML + 加一个 Python 文件，**不需要动任何框架代码**。

### ④ 统一 Finalizer —— 一个声音，只讲一次

不再给每个 skill 套一层"润色"，finalizer **只在整条链路末尾跑一次**，一次性读取 `intent + older_context + recent_context + 所有 step 结果`。解决两个实际问题：

- **风格一致**：skills 只产结构化 artifact，不产散文 —— 周报和退订报告听起来就是同一个助手。
- **跨步综合**：一轮内跑多个 skill 时，finalizer 能一次性表达（"我做完了周报**并且**已经发给 Sarah"）。

### ⑤ 退订状态机 —— "搜索负责发现，状态负责展示"

退订流程最能体现**有状态 AI** 的设计价值。朴素做法是每次都重新搜邮箱，结果已退订的商家会反复出现。Cake 把"发现"和"展示"分开：

```
每次查询  →  实时搜索 Gmail  →  聚合 candidate
          →  合并到本地状态文件（从不删除）
          →  过滤掉 status = hidden_locally_after_unsubscribe
          →  只返回"仍可见"的视图
```

执行层原生支持**多目标**（"退订 JB Hi-Fi 和 Louis Vuitton"），优先使用当前列表里的候选；定位不到时自动触发**针对该目标的再搜索**，而不是直接报错。响应永远把结果拆成 *本轮新退订 / 本地已退订 / 未定位 / 需手动处理*，不会对成功情况撒谎。

> **场景 —— 用户说"退订 Qudos Bank、JB Hi-Fi 和 Louis Vuitton"**
> Resolver 一次提取三个 `target_queries`。Qudos Bank 命中当前列表 → 走一键 POST。JB Hi-Fi 本地已标记隐藏 → 归类为*已退订*，**不重复执行**。Louis Vuitton 不在列表里 → runtime 针对该目标再查询一次，聚合新候选后走 mailto，并回写本地状态。Finalizer 最终给出清晰的三桶汇总。

### ⑥ Agent Step 的结构化 JSON 输出

Planner 放入 `type: agent` 的步骤时，主 agent **不再直接对用户开口**，而是输出：

```json
{ "status": "completed", "artifact": { "kind": "agent_result", "summary": "...", "data": {} }, "reason": "..." }
```

这样 skill step 和 agent step 就是**同构的中间结果**。Finalizer 读到的是一条统一的 artifact 流，不需要判断每一段是哪类 LLM 产的。

### ⑦ 上下文窗口纪律

意图层接收的是硬切分的上下文：`older_context`（≤40 条）+ `recent_context`（≤10 条），用显式标签分段。**工具调用 trace 从不注入**，先被压成自然语言摘要。近期对话通过 prompt 结构加权，而不是靠截断，所以"好的，就那个"这类极简后续能被正确解析，**不必把 200 条历史塞进每一次调用**。

### ⑧ 自维护的用户记忆

三个 Markdown 文件 —— `USER_PROFILE.md` / `USER_HABITS.md` / `WRITING_STYLE.md` —— 由 **专门的写入 agent** 在会话后生成。写作风格通过 `writing_style_profile` 技能从你**自己发出去的邮件**反推，回复草稿用的是*你的*语气，不是 AI 腔。文件是可读可编辑的明文，不藏在数据库里。

### ⑨ 日历审批插件

创建会议走一个 **ReAct 插件**，在真正调用修改性日历 API 之前暂停，先把预览交给用户。LLM 在用户点确认之前**永远看不到**"日历已创建"的回执 —— 堵住了 agent 系统中典型的"静默副作用"类 bug。

### ⑩ 提供商无关的邮件后端

`LINKED_GMAIL` / `LINKED_OUTLOOK` 是切换邮件提供商的唯一开关。工具实例在启动时根据 env 动态装配，并用一个兼容 mixin 抹平 OpenAI 风格工具 schema 在不同 SDK 间的差异。**同一套 skill 层，适用两种邮箱。**

## 🏗️ 架构设计

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

## 🚀 快速开始

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

## 🧩 目录结构

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

## ⚙️ 配置说明

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

## 🧪 本地开发

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
<sub>Made with 🎂 by <b>UNSW COMP9900 Team H16C</b></sub>
</div>
