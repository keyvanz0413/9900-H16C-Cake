# Skill: `weekly_email_summary`

## 目标

在给定天数窗口内（默认 7 天、上限由技能自身保护）总结收件箱。产出给 Finalizer 使用的结构化 bundle，Finalizer 负责按类别（通知 / 待回复 / 订阅 / 其他）输出有序清单。

代码：`email-agent/skills/weekly_email_summary.py`。

---

## 输入

`registry.yaml`：

```yaml
input_schema:
  days:
    type: int
    default: 7
    required: false
  max_results:
    type: int
    default: 200
    required: false
```

由 [Skill Input Resolver](../orchestration/skill-input-resolver.md) 按用户自然语言填入。

---

## 工具使用

`used_tools`（只能调用这 4 个）：

- `search_emails` —— 拉取 `in:inbox newer_than:Nd` 的列表
- `get_email_body` —— 按需取正文
- `list_labels` —— 附带用户当前的标签结构
- `list_drafts` —— 提示 Finalizer 哪些邮件已经有草稿

---

## Bundle 结构

```
[WEEKLY_EMAIL_SUMMARY_BUNDLE]
skill_name: weekly_email_summary
days: 7
max_results: 200
notes:
- Finalizer instruction: 按「需要回复 / 日常通知 / 营销订阅 / 其他」分组，并按时间倒序。
- ...

[SEARCH_EMAILS] ...
[LIST_LABELS] ...
[LIST_DRAFTS] ...
[EMAIL_BODY_1] ...
[EMAIL_BODY_N] ...
```

---

## Finalizer 期望

- 开头一句话概括"这周收了多少封、大致是什么类型"。
- 按上面四组输出有序列表，每条：主题 + 发件人 + 短摘要。
- 在可立即决定的项上给出建议（回复 / 忽略 / 退订）。
- 不虚构未出现在 bundle 中的邮件。

---

## 使用时机（Planner 信号）

- 用户问"最近邮件怎么样 / 这周收到什么 / 过去几天有什么值得看"。
- 组合步骤的前置：先 summary 再让 `main` agent 挑其中一封起草回复。
