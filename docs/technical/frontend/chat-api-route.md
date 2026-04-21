# `/api/chat` 路由

## 目标

`oo-chat/app/api/chat/route.ts` 是 Next.js Server Route，承担两件事：

1. **Agent 转发**：把前端的对话请求包装成 ConnectOnion Ed25519 签名消息，POST 给 `{agentUrl}/input`。
2. **LLM 直连**：没有 agent URL 时，直接用 `connectonion` SDK 的 `createLLM` 调 LLM。

---

## 请求体

```ts
POST /api/chat
{
  message: string,
  messages: ChatMessage[],          // 历史（仅 LLM 直连模式使用）
  apiKey?: string,
  model?: string,                   // 例 "co/gemini-2.5-flash"
  agentUrl?: string,
  agentSession?: unknown,           // 上一轮的 session，用于多轮
  useDefaultAgent?: boolean,
}
```

`resolvedAgentUrl = agentUrl || (useDefaultAgent ? env.DEFAULT_AGENT_URL : '')`。

---

## Agent 模式

### 身份解析

```ts
// URL 形如 https://{name}-{shortAddress}.agents.openonion.ai
const addressMatch = resolvedAgentUrl.match(/-(0x[a-f0-9]+)\./i)
let agentAddress = addressMatch ? addressMatch[1] : ''

// 本地 URL（localhost）没有地址，就 fallback 到 /info 端点
if (!agentAddress || agentAddress.length < 66) {
  const info = await fetch(`${resolvedAgentUrl}/info`).then(r => r.json())
  agentAddress = info.address || ''
}
```

### 签名

```ts
const payload = {
  prompt: message,
  to: agentAddress,
  timestamp: Math.floor(Date.now() / 1000),
}
const canonical = canonicalJSONString(payload)   // sort_keys + ascii-escape
const signature = address.sign(serverKeys, canonical)

const body = { payload, from: serverKeys.address, signature }
if (session) body.session = session
```

`canonicalJSONString` 匹配 Python 端 `json.dumps(..., sort_keys=True, separators=(",", ":"), ensure_ascii=True)`，确保两端 hash 一致。

### 转发

```ts
fetch(`${resolvedAgentUrl}/input`, { method: 'POST', body: JSON.stringify(body) })
```

返回：`{ response, session }`。前端把 `session` 存下来，下一次一起带过来。

---

## LLM 直连模式

- 只在没有 `resolvedAgentUrl` 时启用。
- 把 history + 新消息组成 OpenAI 风格的 `messages`，默认 model `co/gemini-2.5-flash`。
- 无 tool 调用 / 无 agent 状态。

---

## Server Keys 管理

```ts
let serverKeys: ReturnType<typeof address.load> = null

function getServerKeys() {
  if (serverKeys) return serverKeys
  serverKeys = address.load(join(process.cwd(), '.co')) || address.generate()
  return serverKeys
}
```

- 单例缓存；模块级变量，一次生成后在内存里直到进程重启。
- **不写回磁盘**：生产环境应该预先 `co address generate` 然后把私钥持久化到 `.co/`，否则每次重启都会换身份，agent 端信任关系会失效。
- 代码里明确标注了这是一个 TODO：`Production should persist keys to avoid changing identity`。

---

## 错误处理

- Agent 返回非 2xx → 读文本体，返回 `{error: "Agent error: ..."}` + 原状态码。
- Agent 返回成功但没有 `response`/`content`/`result` → 用 `JSON.stringify(data)` 兜底。
- LLM 模式里异常会沿 SDK 冒泡；Next.js 默认会包成 500。

---

## 与审批握手的关系

前端的审批 UI（见 [approval-ui](approval-ui.md)）用的是 **长连接/事件流**（由 ConnectOnion 运行时注入的 `agent.io.send/receive`），不走 `/api/chat`。`/api/chat` 只处理同步的"一问一答"消息。

---

## 环境变量

| 变量 | 作用 |
|---|---|
| `DEFAULT_AGENT_URL` / `NEXT_PUBLIC_DEFAULT_AGENT_URL` | 默认 agent URL |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | LLM 直连模式 |
| `NEXT_PUBLIC_USE_DEFAULT_AGENT` | 前端决定是否显示 default agent home |
| `NEXT_PUBLIC_DEFAULT_AGENT_NAME` | Default agent 显示名 |

Next.js 约定：带 `NEXT_PUBLIC_` 前缀才会暴露到浏览器，其他只在 server route 可读。
