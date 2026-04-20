<div align="center">

# AI Email Agent

**意图驱动的多智能体邮件工作台。**
用自然语言读信、搜信、分拣、回复、退订。

**中文** · [English](README.md)

</div>

---

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
├── README.md                       # 英文说明
├── README.zh-CN.md                 # ← 当前文档
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

### 已完成功能

- [x] 聊天界面
- [x] 智能邮件草稿
- [x] 写作风格学习
- [x] 紧急邮件识别
- [x] 每周邮件总结
- [x] 会议调度
- [x] 退订管家

### 项目亮点

- [x] 多智能体意图层 —— 意图 → 规划 → 参数解析 → 执行 → 定稿
- [x] 声明式技能注册 —— YAML 契约（`scope` / `used_tools` / `input_schema`）
- [x] 双栈邮件提供商 —— Gmail **加** Outlook，一个环境变量切换
- [x] 扩展技能 —— `bug_issue_triage`、`resume_candidate_review`、`init_crm_database`
- [x] 有状态退订 —— 本地状态过滤掉已退订发件人，避免重复打扰
- [x] 日历审批插件 —— 写入型日历调用在执行前暂停并向用户预览
- [x] 自维护用户记忆 —— `USER_PROFILE.md` + `USER_HABITS.md` 由专用写入 agent 自动更新
- [x] 一键 Docker Compose 部署

## 👥 团队

**UNSW COMP9900 · Team H16C**

- Haokun Yang
- Haoyuan Xiang
- Lucia Luo
- Qifan Zhuo
- Wenyu Ding
- Zenglin Zhong

## 📜 许可证

Apache License 2.0 — 详见 [`email-agent/LICENSE`](email-agent/LICENSE)。

## 🙌 致谢

基于 [ConnectOnion](https://connectonion.com) 构建 —— 它为本项目提供了工具层、记忆层与插件机制。

---

<div align="center">
<sub>Made with by <b>UNSW COMP9900 Team H16C</b></sub>
</div>
