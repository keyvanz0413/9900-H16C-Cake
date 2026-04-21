# Calendar Approval Plugin

## 目标

拦截日历写操作，走一次用户审批。ConnectOnion `before_each_tool` 钩子在工具真正执行前触发，本插件据此判断是否放行。

代码：`email-agent/plugins/calendar_approval_plugin.py`。仅在 Gmail 分支被挂载（`agent.py`）。

---

## 拦截的工具

```python
WRITE_METHODS = ("create_event", "create_meet", "update_event", "delete_event")
```

读类工具（`list_events`、`search_events` 等）直接放行。

---

## 三种审批通道

插件按优先级逐级回退：

### 1. 前端 IO（优先）

```python
if getattr(agent, "io", None):
    _request_frontend_approval(...)
```

发送 `{type: "approval_needed", tool, arguments, description}` 到前端；`_wait_for_approval_response` 阻塞等待 `APPROVAL_RESPONSE`。响应字段：

| 字段 | 说明 |
|---|---|
| `approved` | `true` 通过；`false` 拒绝 |
| `scope` | `session` 可选——该工具在本 session 后续免审批 |
| `mode` | 拒绝类型：`reject_hard` / `reject_explain` / 其他 |
| `feedback` | 用户留言 |

三种拒绝模式差异：

- `reject_hard` —— 写入 `current_session["stop_signal"]` 停止本轮所有后续动作。
- `reject_explain` —— 抛错并在错误中嵌入系统提示，要求 main agent "用白话解释这次日历动作 + 为什么、下一步"；**不允许自动重试写入**。
- 其他 —— 一般拒绝，要求不要自动重试，先问用户。

### 2. CLI `pick`（无 IO 但有终端）

`_has_interactive_terminal()` 为真时，用 `connectonion.tui.pick` 在终端弹三个选项：

- `Yes, <action>`
- `Auto approve all calendar actions this session`（设 `calendar_approve_all=True`）
- `No, tell agent what I want`（读一行 feedback 后抛错）

### 3. 无头回退

既无 IO 也无 TTY（典型：纯 HTTP / background 作业）：**直接 return**，让工具继续执行。

> 这是一个"部署模式兜底"：在没有通道可以找人批的环境里，插件不能无限期阻塞；由部署方自己决定是否在更上游层（前端 / 产品逻辑）限制写操作。

---

## 自动放行

```python
def _is_auto_approved(agent, tool_name) -> bool:
    session = agent.current_session
    if session.get("calendar_approve_all", False):
        return True
    return tool_name in session.get("calendar_approved_tools", set())
```

- `calendar_approve_all` —— CLI 的"Auto approve all" 或前端的 session 级放行都会打上。
- `calendar_approved_tools` —— 前端返回 `scope=="session"` 时，把当前工具名加入集合。

**作用域限 session**：Agent 重启后不保留。

---

## Preview 构造

`_build_preview(tool_name, args)` 用 `rich.Text` 构造人类可读的预览块：

- `create_event`：Title / Start / End / Attendees（标黄） / Location / Description
- `create_meet`：同上加"会收到 Meet 邀请"提示
- `update_event`：Event ID + 具体字段变化
- `delete_event`：红字强调永久删除

前端把整段预览放进 approval UI，CLI 通过 Rich Panel 输出。

---

## 对接前端的握手

```json
→ { "type": "approval_needed", "tool": "create_event",
    "arguments": {...}, "description": "Create calendar event 'X'" }
← { "type": "APPROVAL_RESPONSE", "approved": true|false,
    "scope": "once|session", "mode": "...", "feedback": "..." }
```

`agent.io.send(...)` / `agent.io.receive()` 由 ConnectOnion 的运行时在前端模式下注入。断开连接时 `_wait_for_approval_response` 抛 "Connection closed" 错误。

---

## Checkpoint

`_checkpoint(agent)` 调用 `agent.storage.checkpoint(agent.current_session)`，把审批请求前的 session 状态落盘。好处：如果用户在审批页停留很久 / 连接断了，重连时能恢复到"等待审批"的位置。

---

## 不做什么

- 不覆盖 `after_each_tool`——审批只在前置。
- 不做速率限制 / 频率控制——被拒之后是否重试由 agent 侧逻辑决定。
- 不自动从历史对话里推断"用户本来就批了"——每一次写操作都要有 session 级或显式审批标记。
