# Approval UI

## 目标

当 `calendar_approval_plugin` 要求审批时，前端要弹一个可读面板让用户点"通过 / 拒绝 / 要求解释"。本文档描述 `oo-chat` 侧的交互约定。

代码相关：`oo-chat/components/chat/chat-tool-approval.tsx` 及 `use-agent-sdk.ts`。

---

## 协议

### Agent → 前端

由 ConnectOnion 的运行时通道发出（不是 `/api/chat` 响应）：

```json
{
  "type": "approval_needed",
  "tool": "create_event | create_meet | update_event | delete_event",
  "arguments": { ... },
  "description": "Human-readable summary"
}
```

详见 [calendar-approval-plugin](../providers/calendar-approval-plugin.md)。

### 前端 → Agent

```json
{
  "type": "APPROVAL_RESPONSE",
  "approved": true | false,
  "scope": "once | session",
  "mode": "reject_hard | reject_explain | reject_other",
  "feedback": "用户可选留言"
}
```

- `approved=true` → 工具继续执行。
- `approved=true` + `scope=="session"` → 当前工具在本 session 后续免审批。
- `approved=false` + `mode=="reject_hard"` → 彻底停止本轮后续动作。
- `approved=false` + `mode=="reject_explain"` → agent 改为"先解释再问"的策略，不自动重试。
- `approved=false` + 其他 → 普通拒绝，agent 会停下问用户"要改什么"。

---

## UI 结构

`chat-tool-approval.tsx` 消费 `approval_needed` 事件后渲染：

1. **标题**：来自 `description`（例 "Create calendar event 'X'"）。
2. **预览区**：把 `arguments` 中的关键字段用 key:value 列出。attendees / delete 这类敏感项 UI 中高亮。
3. **动作区**：
   - "Approve" → `approved=true, scope=once`
   - "Approve for this session" → `approved=true, scope=session`
   - "Reject" → `approved=false, mode=reject_hard`
   - "Ask for explanation" → `approved=false, mode=reject_explain`
   - "Tell agent what to change" → `approved=false, mode=reject_other`，附 feedback 输入

---

## 阻塞语义

- agent 在 `_wait_for_approval_response` 里阻塞直到收到响应。
- 若 UI 侧长时间没回应，ConnectOnion 保持连接；超时 / 断线时 agent 会抛 "Connection closed while waiting for Calendar approval." 并把当前 step 记为 failed。
- **checkpoint**：发送 `approval_needed` 前，agent 调 `storage.checkpoint(current_session)`，把会话状态落盘，支持在另一客户端/另一个浏览器标签重连时恢复到审批位置。

---

## 为什么不做在 `/api/chat` 里

- 审批需要 **推** 给前端；HTTP request/response 周期很难表达。
- ConnectOnion 的 io 通道天然是双向；前端用事件流订阅，agent 用 `send/receive` 推送。
- 把审批放在 `/api/chat` 的同步响应里会把等待阻塞在单次 fetch 上，体验很差。

---

## 前端未接入通道时

`calendar_approval_plugin` 会回退到 CLI 或无头模式（见 plugin 文档）。`oo-chat` 的 Address Book 模式没有接审批通道时，日历写操作会被无头模式放行。 **只有 Default Agent 页面默认接上了 approval 流**；Address Book 模式需要使用者自己决定是否打开。
