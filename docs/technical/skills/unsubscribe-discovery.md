# Skill: `unsubscribe_discovery`

## 目标

列出 **当前可退订的订阅源**：实时扫描收件箱、合并到本地状态文件，再按"可见（active）"过滤后返回给 Finalizer。不执行任何退订动作。

代码：`email-agent/skills/unsubscribe_discovery.py`，依赖 [`unsubscribe_workflow`](../unsubscribe/unsubscribe-workflow.md) 与 [`unsubscribe_state`](../unsubscribe/unsubscribe-state.md)。

---

## 输入

```yaml
input_schema:
  days:        { type: int, default: 30, required: false }  # clamp 到 1..MAX_DAYS(90)
  max_results: { type: int, default: 100, required: false } # clamp 到 1..MAX_RESULTS_CAP(250)
```

---

## 流程

1. `build_discovery_search_query(days)` —— 构造 Gmail 查询：`in:inbox newer_than:Nd (unsubscribe OR newsletter OR ...)`。
2. `collect_candidates(...)` —— 调 `search_emails` + `get_unsubscribe_info`，把匹配邮件归并到每发件人一个 candidate；保存 `method`（one_click / mailto / website）、`representative_email_id`、`risk_level` 等。
3. `merge_discovered_candidates(...)` —— 增量并入 `UNSUBSCRIBE_STATE.json`（新 insert / 已有 update）。
4. `visible_unsubscribe_state_records(...)` —— 过滤掉状态为 `hidden_locally_after_unsubscribe` 的条目。
5. 把 visible candidates 序列化成 JSON，连同元数据拼成 bundle。

---

## 实时 + 状态的原因

- **实时扫描**：订阅状态随时变化（退订过的也可能被重新订阅），不能完全信任旧快照。
- **本地状态**：部分订阅源没有机器可读的 `List-Unsubscribe`，用户只能通过 mailto / 网站手工退订；退订过之后我们把它标记 `hidden_locally_after_unsubscribe`，防止下次再被推荐。
- **过滤而非删除**：hidden 记录仍保留在 JSON 中，便于审计与恢复。

---

## Bundle 字段

```
[UNSUBSCRIBE_DISCOVERY_BUNDLE]
skill_name: unsubscribe_discovery
days: N
max_results: N
search_query: ...
matched_email_id_count: N
live_discovered_candidate_count: N
inspected_email_count: N
metadata_error_count: N
state_inserted_count: N
state_updated_count: N
visible_candidate_count: N
hidden_local_candidate_count: N
notes:
- 总是先做活扫描再返回。
- 结果已过滤掉本地已退订。
- 没有执行任何 POST / mailto / 网页 / 归档动作。
- 呈现时请附 representative_email_id。

[SEARCH_EMAILS] ...
[GET_UNSUBSCRIBE_INFO] ...
[VISIBLE_CANDIDATES_JSON]
[
  {
    "candidate_id": "...",
    "sender_email": "...",
    "sender_name": "...",
    "method": "one_click|mailto|website|unknown",
    "representative_email_id": "...",
    "risk_level": "low|medium|high",
    "status": "active",
    ...
  },
  ...
]
```

---

## Finalizer 期望

- 用户中文 → 输出中文表格或清单。
- 列出可见 candidate：发件人（名称 + 邮箱）+ 方法 + 风险等级 + representative_email_id。
- 明确告知："要执行哪几个？"——因为执行由下一步的 `unsubscribe_execute` 完成。
- 不要声称"已经退订"。

---

## 使用时机

- 用户说"列出我订阅的东西 / 看看我订了什么 / 列退订列表"。
- `unsubscribe_execute` 之前的前置步骤（虽然 execute 本身可以独立触发定向发现）。
