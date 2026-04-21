# Skill: `bug_issue_triage`

## 目标

按"bug / 事故 / 构建失败 / 测试失败 / 回归"这类关键词扫描收件箱，为工程师产出可按优先级排序的 bug 邮件清单。

代码：`email-agent/skills/bug_issue_triage.py`。

---

## 常量

```python
SEARCH_MAX_RESULTS = 350
MAX_LOOKBACK_DAYS = 7
BUG_QUERY_TERMS = (
    "bug", "bugs", "defect", "regression",
    '"build failed"', '"build failure"',
    '"failing tests"', '"tests failed"', '"test failed"',
    '"ci failed"', '"pipeline failed"',
    '"issue opened"', '"incident opened"',
    '"production issue"', '"prod issue"',
    "incident", "outage", "broken", "failure", "blocker",
    '"error report"',
)
```

---

## 流程

1. 用 `_build_bug_query(days)` 拼接 Gmail 查询：
   `in:inbox newer_than:{days}d ({term1} OR {term2} OR ...)`
2. 调 `search_emails` 拿到匹配邮件，最多 350 条。
3. 用正则 `^\s*ID:\s*(\S+)\s*$` 从 `search_emails` 文本结果里抽 email id。
4. 对每一个 id 调 `get_email_body`。
5. 把所有原始输出拼成 bundle 返回。

---

## Bundle 关键字段

```
[BUG_ISSUE_TRIAGE_BUNDLE]
skill_name: bug_issue_triage
days: 7
search_query: ...
bug_keywords: ...
matched_email_count: N
body_fetch_count: N
notes:
- Finalizer instruction: 按优先级从高到低排序。
- 生产阻塞 / 构建失败 / 测试失败优先于普通通知。
[SEARCH_EMAILS] ...
[MATCHED_BUG_EMAIL_IDS] ...
[EMAIL_BODY_1..N] ...
```

---

## Finalizer 期望

- 首行给结论："过去 N 天共 M 封 bug 相关邮件"。
- 优先级分组：P0 生产/阻塞 → P1 构建/测试失败 → P2 其他。
- 每条：来源（CI / 工单系统 / 人工报告）+ 主题 + 一句动作建议。
- 空结果：告诉用户"没有 bug 相关邮件"，不要编。

---

## 使用时机

- 用户问"最近有什么 bug / 线上挂了吗 / build 有问题吗"。
- 与 `main` agent step 组合：先 triage，再让 agent 发一个跟进邮件或创建日历事件。
