# Skill: `writing_style_profile`

## 目标

重新（或首次）生成用户的 **写作风格画像** 并落盘到 `email-agent/WRITING_STYLE.md`。

代码：`email-agent/skills/writing_style_profile.py`。

这是三大 Markdown 记忆文件中的写作风格一栏，被 `draft_reply_from_email_context` 在起草回复时读取，用来模仿用户语气。

---

## 依赖的子 Agent

来自 `skill_runtime.agents.writing_style_writer`（即 `agent.py` 中构造的 `writing_style_writer_agent`）。没有这个 Agent 时技能直接抛 `RuntimeError`。

写手的提示词在 `email-agent/prompts/writing_style_writer.md`，输出契约：

```json
{
  "writing_style_markdown": "# Writing Style\n\n## Tone\n...\n## Structure\n...\n## Signature cues\n...",
  "user_summary": "一两句话向用户描述这次更新的结论",
  "reason": "用于调试的简短说明"
}
```

---

## 流程

1. 解析 `WRITING_STYLE.md` 现有内容：空 / 不存在 → 使用默认占位；有内容 → 作为 `update_existing_profile` 模式。
2. 调 `get_sent_emails(max_results=30)` 拉用户近 30 封 **已发送** 邮件。
3. 拼装 prompt：
   ```
   [UPDATE_MODE] update_existing_profile | create_new_profile
   [CURRENT_WRITING_STYLE] ...
   [RECENT_SENT_EMAILS] ...
   ```
4. `writer_agent.input(prompt, max_iterations=1)`；`_extract_json_payload` 容错剥围栏。
5. 校验三个必填字段非空 → 覆写 `WRITING_STYLE.md` → 返回 bundle。

`max_iterations=1`：写手只负责一次整合，不循环推理、不调工具。

---

## Bundle 输出

```
[WRITING_STYLE_PROFILE_UPDATED]
skill_name: writing_style_profile
action: created | updated
path: .../WRITING_STYLE.md
sample_size: 30

[WRITING_STYLE_SUMMARY]
<user_summary>

[WRITING_STYLE_MARKDOWN]
<完整 Markdown 内容>
```

---

## Finalizer 期望

- 确认动作：**创建** 还是 **更新**。
- 把 `user_summary` 作为主要内容回传给用户。
- 不需要把整份 Markdown 吐给用户——文件已经落盘，用户可直接打开。
- 如果用户明确问"写作风格长什么样"，可以简要引用前面几条。

---

## 使用时机

- 用户主动说"重新分析我的写作风格 / 学习我的邮件风格 / 更新写作风格"。
- 不应在 Planner 里"自动插入"——这是一次 LLM + 文件写操作，有成本且更新频率不该太高。
