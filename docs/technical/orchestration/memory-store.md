# Markdown Memory Store

## 概览

Orchestrator 的记忆层落盘在 **三份 Markdown 文件** 上，而不是数据库：

| 文件 | 用途 |
|---|---|
| `email-agent/USER_PROFILE.md` | 用户身份、角色、长期偏好 |
| `email-agent/USER_HABITS.md` | 行为习惯（处理邮件的时段、分组方式等） |
| `email-agent/WRITING_STYLE.md` | 用户的书面风格画像 |

读写都走 `MarkdownMemoryStore`（见 `email-agent/intent_layer.py`）。

---

## 读：直读 Markdown

```python
store.read_profile()   # 返回 USER_PROFILE.md 全文
store.read_habits()    # 返回 USER_HABITS.md 全文
```

这两个文件会被注入到 Intent / Planner / Main Agent 的系统提示中，作为"用户画像"。

`WRITING_STYLE.md` 只在草稿类技能（如 `draft_reply_from_email_context`）里被读取，避免污染其他场景。

---

## 写：交给写手 Agent

记忆文件不是 LLM 直接覆写，而是经过 **写手子 Agent**：

| 写手 | 负责文件 | 触发场景 |
|---|---|---|
| `user_memory_writer_agent` | `USER_PROFILE.md` / `USER_HABITS.md` | Finalizer 完成后，对本轮 `MemoryUpdate` 做整合 |
| `writing_style_writer_agent` | `WRITING_STYLE.md` | `writing_style_profile` 技能运行时调用 |

提示词位于 `email-agent/prompts/user_memory_writer.md` 与 `writing_style_writer.md`。

---

## 更新流程

1. **Intent 阶段**：Intent Agent 产出 `user_update_summary`（本轮对用户画像的观察）。
2. **Finalizer 阶段**：产出面向用户的回复文本。
3. **`MemoryUpdate` 组装**：orchestrator 把 summary + Finalizer 的回复 + 本轮用户消息送给写手。
4. **`apply_update()`**：
   - 读取当前 `USER_PROFILE.md` / `USER_HABITS.md`。
   - 把原文 + update 作为上下文交给 `user_memory_writer_agent`。
   - 写手返回更新后的整份 Markdown，`MarkdownMemoryStore` 覆写落盘。

写手被设计为 **保守更新**：相同事实不会重复记录，明显自相矛盾的旧条目会被改写，但不会丢弃"未过时的"内容。

---

## 数据形状建议

`USER_PROFILE.md` 推荐结构：

```markdown
# Profile
- Role: ...
- Timezone: ...
- Email cadence: ...

# Long-term goals
- ...

# Preferences
- ...
```

`USER_HABITS.md` 推荐结构：

```markdown
# Observed habits
- [2026-04-14] 通常在下午处理订阅类邮件
- [2026-04-15] 对 Jira 邮件会先看标题再决定是否打开
```

`WRITING_STYLE.md` 的写手会输出三块：**tone / structure / signature cues**。详见 [writing-style-profile 技能](../skills/writing-style-profile.md)。

---

## 失败隔离

- **写手异常** → 仅记录 warning，不影响本轮给用户的回复。
- **文件不可写** → 同上。
- **apply_update 只在 Finalizer 成功时调用**：确保失败路径不污染长期记忆。

---

## 不做什么

- 不存结构化数据（没有 json / sqlite 记忆）。
- 不按对话逐条追加："记忆"是 **对话级** 的，而不是消息级的。
- 不在多 Agent 之间做写锁：只有写手 Agent 可以覆写这三份文件。
