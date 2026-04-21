# Skill Registry

## 概览

所有技能在 `email-agent/skills/registry.yaml` 中声明；运行时由 `PythonSkillExecutor` 读取并动态加载 `skills/<name>.py`。

Planner 读 `registry.yaml` 选技能，Skill Input Resolver 读 `input_schema` 构造参数，执行器读 `used_tools` 决定注入哪些工具。

---

## YAML 字段

每个技能一个 top-level 键，键名即技能名。

```yaml
weekly_email_summary:
  description: Summarize recent inbox activity for a given window.
  scope: read-only | write
  used_tools:
    - search_emails
    - get_email_body
    - list_labels
    - list_drafts
  input_schema:
    days:
      type: int
      default: 7
      required: false
      description: Lookback days, capped at 30.
    max_results:
      type: int
      default: 200
      required: false
  resolver_guidance: |
    Infer "days" from user's phrase like "this week" (7) / "past month" (30).
```

| 字段 | 作用 |
|---|---|
| `description` | 给 Planner 看的技能用途，影响选择 |
| `scope` | `read-only` 与 `write` 用来给前端 / 审批层打标签 |
| `used_tools` | 技能内部允许调用的工具；未列出的工具不会被注入 |
| `input_schema` | Resolver 目标 schema |
| `resolver_guidance` | 给 `skill_input_resolver_agent` 的私货提示 |

---

## 技能实现契约

每个 `skills/<name>.py` 必须导出：

```python
def execute_skill(*, arguments, used_tools, skill_spec, skill_runtime=None,
                  step_goal=None, read_results=None) -> dict:
    ...
    return {
        "completed": True,
        "response": bundle_text,
        "reason": "...",
    }
```

| 入参 | 说明 |
|---|---|
| `arguments` | 已通过 `validate_skill_arguments` 的参数字典 |
| `used_tools` | `{"tool_name": callable}`，仅包含 `used_tools` 声明的工具 |
| `skill_spec` | registry 条目原文 |
| `skill_runtime` | 可选：orchestrator 注入的运行时上下文（部分技能用到写手子 Agent） |
| `step_goal` | Planner 的 `goal` 字符串 |
| `read_results` | `reads` 指向的上游 step 的结构化结果 |

返回字典要点：

- **`response`** 必须是给 Finalizer 读的字符串包（通常以 `[XXX_BUNDLE]` 开头）。
- **`completed`** 表示技能是否走完；失败也可以 `completed=True`，但 `response` 里要说明原因。
- **`reason`** 写给 orchestrator 日志。

---

## 常见 Bundle 结构

技能的 `response` 普遍采用"带节标题的纯文本块"：

```
[WEEKLY_EMAIL_SUMMARY_BUNDLE]
skill_name: weekly_email_summary
days: 7
notes:
- ...
- Finalizer instruction: ...

[SEARCH_EMAILS]
tool: search_emails
arguments: {...}
<raw tool output>

[EMAIL_BODY_1]
tool: get_email_body
email_id: ...
<raw tool output>
```

这种形式的两个好处：

- Finalizer 看到结构化段落边界，不会把工具原始输出当事实。
- 便于在 trace 里 diff 每一步的技能输出。

---

## 加新技能的步骤

1. **写实现**：`skills/my_skill.py`，导出 `execute_skill`。
2. **登记**：在 `registry.yaml` 新增一个 top-level 条目。
3. **提供 resolver 样例**：`resolver_guidance` 尽可能明确（自然语言 → 参数映射）。
4. **（可选）为 Planner 提供选择信号**：`description` 中写清楚"什么场景下选我"。
5. **端到端验证**：`make backend-agent-test`。

新技能 **不需要改 Planner 或 Finalizer 提示词**——这是该架构的核心价值。

---

## 当前登记的技能

| 名称 | scope | 摘要 |
|---|---|---|
| `weekly_email_summary` | read-only | 过去 N 天邮件概览 |
| `urgent_email_triage` | read-only | 按紧急词拉邮件 |
| `bug_issue_triage` | read-only | 按 bug/故障词拉邮件 |
| `resume_candidate_review` | read-only | 按招聘/简历关键词拉邮件 |
| `draft_reply_from_email_context` | write | 基于未回邮件 / 搜索结果起草回复 |
| `send_prepared_email` | write | 把现成草稿 `to/subject/body` 发出 |
| `writing_style_profile` | write | 更新 `WRITING_STYLE.md` |
| `unsubscribe_discovery` | read-only | 列出可退订源 |
| `unsubscribe_execute` | write | 真正执行退订 |

各自详情见本目录下对应文档。
