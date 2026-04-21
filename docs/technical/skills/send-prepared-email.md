# Skill: `send_prepared_email`

## 目标

执行一次"把一封已完全定稿的邮件发出去"的动作。它假设 `to / subject / body` 都已经明确可用（来自上一步 `draft_reply_from_email_context` 或用户直接给出）。

代码：`email-agent/skills/send_prepared_email.py`。

---

## 输入契约

```yaml
input_schema:
  to:      { type: str, required: true }
  subject: { type: str, required: true }
  body:    { type: str, required: true }
  cc:      { type: str, required: false }
  bcc:     { type: str, required: false }
```

Resolver 在这一步尤其严格：如果 `reads` 的 artifact 里没有明确字段，必须 fail-fast，而不是让模型造一个 `to`。

---

## 流程

1. 拼 `send` 的 kwargs：`{to, subject, body}` + 可选 `cc` / `bcc`。
2. 调用 provider 的原生 `send` 工具（Gmail 的 `gmail.send` 或 Outlook 的等价物）。
3. 把原始返回文本作为 `[SEND_EMAIL_RESULT]` 段落放入 bundle。
4. 通过字符串 `"email sent successfully"` 检测成功与否，在 `reason` 里标注。

**不做二次校验**：收件人、正文等格式问题留给 provider 工具处理。

---

## Bundle 关键段

```
[SEND_PREPARED_EMAIL_RESULT]
skill_name: send_prepared_email
notes:
- 仅当发送结果表明成功时 Finalizer 才能说"已发送"。
- 发送失败必须明确报告，不得声称成功。

[SEND_EMAIL_RESULT]
tool: send
arguments: {...}
<原始工具返回>

[SENT_EMAIL_FIELDS]
to: ...
cc: ...
bcc: ...
subject: ...
body:
...
```

---

## Finalizer 期望

- **成功**：一句确认 + 要点（收件人 / 主题）。
- **失败**：告诉用户失败原因（来自原始返回），并建议下一步（重试 / 修改内容）。
- 永远不要把 `body` 原文再全量吐给用户——用户刚写的东西。

---

## 写操作 + 插件副作用

发件成功会被 [gmail-sync-plugin](../providers/gmail-sync-plugin.md) 捕获，自动更新 CRM 的 `last_contact`。这个副作用发生在 `after_each_tool` 钩子里，技能自己不感知。
