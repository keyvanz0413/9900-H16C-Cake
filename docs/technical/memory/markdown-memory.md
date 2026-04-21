# Markdown Memory

## 概览

EmailAI 的"记忆"不是数据库，也不是 embedding，而是 **三份 Markdown 文件** 配合 **写手子 Agent**：

| 文件 | 位置 | 读者 | 写手 |
|---|---|---|---|
| `USER_PROFILE.md` | `email-agent/USER_PROFILE.md` | Intent / Planner / Main Agent | `user_memory_writer_agent` |
| `USER_HABITS.md` | `email-agent/USER_HABITS.md` | 同上 | `user_memory_writer_agent` |
| `WRITING_STYLE.md` | `email-agent/WRITING_STYLE.md` | `draft_reply_from_email_context` skill | `writing_style_writer_agent` |

---

## 为什么用 Markdown

- **对人类友好**：用户想看 / 修改 / 导出都容易。Vector store 没有这种可读性。
- **对 LLM 友好**：整份拼进系统提示，LLM 不需要额外的检索步骤。规模上限 = 几百行。
- **易回滚**：可以 git diff、可以手动编辑、可以复制到新账户。

---

## 读取入口

```python
store = MarkdownMemoryStore(
    user_profile_path=Path("email-agent/USER_PROFILE.md"),
    user_habits_path=Path("email-agent/USER_HABITS.md"),
    writing_style_path=Path("email-agent/WRITING_STYLE.md"),
    user_memory_writer_agent=...,
    writing_style_writer_agent=...,
)

store.read_profile()
store.read_habits()
```

`orchestrator` 在构造 Intent / Planner / main agent 的 system prompt 时，把这两份拼进去；整体长度不做 token 预算控制，期望两份加起来不超过几 KB。

`WRITING_STYLE.md` 的读取由技能自己负责（`draft_reply_from_email_context.py`），不注入到通用 system prompt，避免稀释其他场景。

---

## 写入入口

```python
store.apply_update(
    user_update_summary=...,   # Intent 阶段产出的观察
    final_response=...,         # Finalizer 给用户的回复
    user_message=...,           # 本轮用户消息
)
```

流程：

1. 读当前 `USER_PROFILE.md` / `USER_HABITS.md`。
2. 用固定模板把原文 + update 拼成 prompt（`prompts/user_memory_writer.md`）。
3. 调 `user_memory_writer_agent.input(prompt, max_iterations=1)`。
4. 写手返回 JSON：
   ```json
   {
     "user_profile_markdown": "...",
     "user_habits_markdown": "...",
     "reason": "..."
   }
   ```
5. 覆写 `USER_PROFILE.md` 与 `USER_HABITS.md`。

**只在 Finalizer 成功后调用**，失败路径不触动文件。

---

## 为什么是写手而不是直接 append

Append 会累积噪声：相同事实重复记录、过期事实继续存在、自相矛盾的条目不会被整理。写手通过读整份 Markdown + 本轮 update，做 **整合式重写**：

- 重复事实合并为一条。
- 新观察直接写入。
- 明显过期的旧条目由写手判断是否删除（保守，不轻易删）。
- 保持 Markdown 结构（headings / bullet lists）。

这种方式代价是每次 Finalizer 后多一次 LLM 调用，但对 Opus / Sonnet 级模型可接受。

---

## WRITING_STYLE 的独立性

`WRITING_STYLE.md` 由 [`writing_style_profile` 技能](../skills/writing-style-profile.md) 显式触发：

- 不跟 `apply_update` 连动。
- 每次用 30 封已发送邮件作为原始素材重新生成。
- 写手 agent 独立（`writing_style_writer_agent`），max_iterations=1，不调工具。

这样避免"对话里随手一句话"影响写作风格画像。

---

## 失败与一致性

- **写手返回非法 JSON / 缺字段** → 技能/orchestrator 抛异常；orchestrator 把这次 update 丢掉，不触动文件。
- **磁盘写入失败** → 异常上抛；对外回复已经发出，用户不会感知，但日志里会看到。
- **并发**：当前部署是单进程；不做文件锁。未来多进程需要加锁或改用集中存储。

---

## 路径解析

三份文件的路径在 `agent.py` 中固定：

```python
USER_PROFILE_PATH = BASE_DIR / "USER_PROFILE.md"
USER_HABITS_PATH  = BASE_DIR / "USER_HABITS.md"
WRITING_STYLE_PATH = BASE_DIR / "WRITING_STYLE.md"
```

部署到容器时，建议把 `email-agent/` 目录挂成持久卷，否则重启会丢记忆。
