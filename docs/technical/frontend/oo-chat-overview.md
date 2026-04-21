# `oo-chat` Frontend Overview

## 定位

`oo-chat/` 是 EmailAI 的 Web 客户端，基于 **Next.js 16 + React 19 + Tailwind 4**。它本身不是 email agent 的一部分；通过 HTTP（可选 Ed25519 签名）对接外部 ConnectOnion agent，或直连 LLM 做纯聊天。

仓库里 `oo-chat/CLAUDE.md` 是 chat-ui registry 的上游副本来源，本文只描述本仓库里真实运行的结构。

---

## 目录结构

```
oo-chat/
├── app/
│   ├── page.tsx              # 主入口：默认 Agent 页 or 地址簿页
│   ├── layout.tsx            # 根 Layout（Inter font）
│   ├── globals.css           # Tailwind + 定制样式
│   ├── address/              # "地址簿"模式（添加 / 管理多个 agent）
│   ├── settings/
│   └── api/
│       ├── chat/route.ts     # /api/chat：聊天转发 / LLM 直连
│       └── auth/route.ts     # 身份/认证入口
├── components/
│   ├── chat/                 # 聊天组件集合（消息列表、输入框、审批 UI、等）
│   ├── chat-layout.tsx
│   ├── sidebar.tsx / agent-header.tsx / session-list.tsx
│   └── ui/
├── store/
│   └── chat-store.ts         # Zustand + persist：会话 / agent 列表 / API key
└── hooks/
    ├── use-identity.ts
    └── use-agent-info.ts
```

---

## 两种运行模式

### 1. Default Agent（`NEXT_PUBLIC_USE_DEFAULT_AGENT=true`）

- 页面直接展示一个主 Chat，不需要用户先添加 agent。
- `/api/chat` 里用 `useDefaultAgent=true` 并自动读 `DEFAULT_AGENT_URL` / `NEXT_PUBLIC_DEFAULT_AGENT_URL`。
- 适合容器化部署（compose up 之后就能聊）。

### 2. Address Book（默认）

- 侧栏列出已保存的 agent 地址（公钥 `0x...`）。
- 用户可以添加多个 agent、切换会话。
- Zustand `useChatStore` 持久化 agent 列表 + 会话。

---

## 会话模型

```ts
interface Conversation {
  sessionId: string        // UUID；也是 agent session 标识
  title: string            // 首条用户消息前 30 字
  agentAddress: string     // 0x...
  ui: UI[]                 // 前端展示用事件列表
  createdAt: Date
}
```

- 每次发消息，前端把上一次拿到的 `session` 原样回传给 agent（见 [chat-api-route](chat-api-route.md)），实现多轮状态延续。
- 从 UI 角度看，对话是线性的；orchestrator 的 trace 可以在 UI 里以卡片方式展开。

---

## 组件群（`components/chat/`）

关键文件：

- `chat.tsx` —— 顶层聊天组件。
- `chat-messages.tsx` / `chat-message.tsx` —— 消息列表与单条渲染。
- `chat-input.tsx` —— 输入框 + 键盘快捷键。
- `chat-tool-approval.tsx` —— 接收 `approval_needed` 消息并渲染审批面板（详见 [approval-ui](approval-ui.md)）。
- `chat-ask-user.tsx` —— agent 主动问用户一个问题时使用。
- `ulw-*.tsx` + `mode-*.tsx` —— "Use-Like-Workflow" 相关的模式切换与监控面板。
- `use-agent-sdk.ts` —— 封装对 agent 的调用。

---

## 依赖与构建

- **ConnectOnion TS SDK**：`connectonion`（package 的 dependency）提供 `createLLM`、`address.sign/generate`、`RemoteAgent` 等。
- **Icons**：`react-icons`（HiOutline* Heroicons）。
- **样式**：`tailwind-merge` + `clsx`。

开发命令：

```bash
cd oo-chat
npm run dev      # http://localhost:3000
npm run build
npm run lint
```

Docker 部署下端口被映射为 `3300` (见 `docker-compose.yml`)。

---

## 不做什么

- 不直接嵌入 agent 运行时；所有对话都走 HTTP。
- 不在前端保存 Gmail / Outlook token；只保存 agent 地址与 API key。
- 不做服务端渲染的对话历史；所有历史都在 client 的 Zustand store 里，借助 `persist` 中间件落到 localStorage。
