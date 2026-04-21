# Skill: `urgent_email_triage`

## 目标

用一组"紧急"关键词扫收件箱，拉出需要用户尽快处理的邮件。产出 bundle 供 Finalizer 按紧急度排序呈现。

代码：`email-agent/skills/urgent_email_triage.py`。

---

## 输入

```yaml
input_schema:
  days:
    type: int
    default: 7
    required: false
```

`MAX_LOOKBACK_DAYS = 7`，Resolver 传入更大值会被夹紧。

---

## 工具使用

- `search_emails` 构造查询：`in:inbox newer_than:Nd (urgent OR asap OR "action required" OR ...)`
- `get_email_body` 把搜到的每封邮件正文拉下来

关键词集合（`URGENT_QUERY_TERMS`）涵盖：`urgent`, `asap`, `"action required"`, `"time sensitive"`, `deadline`, `"immediate attention"`, `"respond today"`, `critical`, `priority`, `"blocker"` 等。

---

## Bundle 结构

与 `weekly_email_summary` 相同的 `[*_BUNDLE]` 约定，关键段：

```
[URGENT_EMAIL_TRIAGE_BUNDLE]
skill_name: urgent_email_triage
days: 7
search_query: in:inbox newer_than:7d (...)
matched_email_count: N
body_fetch_count: N
notes:
- Finalizer instruction: 按优先级从高到低排序，生产事故/阻塞类最优先。
[SEARCH_EMAILS] ...
[MATCHED_URGENT_EMAIL_IDS] ...
[EMAIL_BODY_1..N] ...
```

---

## Finalizer 期望

- 最前面给"本轮共 N 封紧急邮件"的一句话结论。
- 高优先级在前：生产事故 > 对外承诺截止 > 内部请求。
- 给每封一句话动作建议。
- 若为空：明确告诉用户"没有紧急邮件"。
