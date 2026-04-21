# Skill: `unsubscribe_execute`

## 目标

真正执行退订。支持两种目标表达（任选其一或混用）：

- `candidate_ids`: 直接给出之前 discovery 产出的 candidate_id 列表
- `target_queries`: 人话 / 关键词，由本技能做一次定向 search + 解析

并返回 **分类的执行结果**：newly_unsubscribed / already_unsubscribed / manual_action_required / failed / not_found。

代码：`email-agent/skills/unsubscribe_execute.py`，依赖 [`unsubscribe_workflow`](../unsubscribe/unsubscribe-workflow.md) 与 [`unsubscribe_state`](../unsubscribe/unsubscribe-state.md)。

---

## 输入

```yaml
input_schema:
  target_queries:  { type: list[str], required: false }
  candidate_ids:   { type: list[str], required: false }
  method:          { type: str, default: "auto" }   # auto|one_click|mailto|website
  days:            { type: int, default: 30 }
  max_results:     { type: int, default: 100 }
```

- `target_queries` 与 `candidate_ids` 不能全部为空，否则直接 `completed: false`。
- `method` 白名单：`{auto, one_click, mailto, website}`。

---

## 解析目标

1. **优先本地 / 已有可见列表**：
   - `candidate_ids` 直接查 `current_visible_by_id` / `state_index`。
   - `target_queries` 在可见列表里匹配发件人名/域/主题（`match_candidates_by_target_query`）。
2. **必要时做定向 live 搜索**：
   - `build_targeted_search_query(query, days)` 精确定位。
   - 命中 1 个 → 解析成功，`selection_source = targeted_search_match`。
   - 命中多个 → 视为 `not_found`（避免误退）。
   - 没命中 → `not_found`。
3. **状态检查**：如果目标在本地状态为 `hidden_locally_after_unsubscribe`，分类为 `already_unsubscribed`，不再执行。

---

## 执行路径

对于解析出的每个候选，调 `get_unsubscribe_info` 获取最新 unsubscribe metadata（`_hydrate_candidates_for_execution`），然后按 `effective_method` 分派：

| method | 工具 | 成功语义 |
|---|---|---|
| `one_click` | `post_one_click_unsubscribe(url)` | `confirmed` / `request_accepted` / `request_submitted` |
| `mailto` | `send({to, subject: "unsubscribe", body})` | `request_sent` |
| `website` | **不自动执行**，给出 `manual_unsubscribe` 链接 | `manual_link_available` |

`requested_method` 与 `classified_method` 不一致时：

- `auto` → 按 `classified_method`；若其不可用则按 `one_click > mailto > website` 顺序回退。
- 显式指定但不可用 → 直接 `failed`，`evidence` 说明"方法不可用"。

失败或不确定、且本地有网页链接时，会自动挂上 `manual_unsubscribe` 让用户手动点。

---

## 状态回写

成功（`status in {confirmed, request_accepted, request_submitted, request_sent}`）的候选会被 `mark_candidates_hidden_after_unsubscribe` 标记为 `hidden_locally_after_unsubscribe`。下一轮 discovery 不再展示。

失败 / manual / not_found 不触动状态。

---

## Bundle 字段

```
[UNSUBSCRIBE_EXECUTE_BUNDLE]
skill_name: unsubscribe_execute
requested_method: auto
days: N
max_results: N
target_query_count: N
candidate_id_count: N
newly_unsubscribed_count: N
already_unsubscribed_count: N
manual_action_required_count: N
failed_count: N
not_found_count: N
notes:
- 不自动打开网站；网站退订只给链接。
- 成功的 one_click / mailto 会被本地隐藏。

[CURRENT_VISIBLE_SUBSCRIPTIONS_JSON] ...
[EXECUTION_GET_UNSUBSCRIBE_INFO] ...
[FALLBACK_DISCOVERY_JSON] ...
[TARGET_RESULTS_JSON] ...
[NEWLY_UNSUBSCRIBED_JSON] ...
[ALREADY_UNSUBSCRIBED_JSON] ...
[MANUAL_ACTION_REQUIRED_JSON] ...
[FAILED_JSON] ...
[NOT_FOUND_JSON] ...
[VISIBLE_SUBSCRIPTIONS_AFTER_EXECUTION_JSON] ...
```

---

## Finalizer 期望

- 按五类标题汇总："已退订 X / 本就退订 Y / 需要手动 Z / 失败 F / 未找到 N"。
- **不自动声称"已退订"**：只有 `newly_unsubscribed` 才能这样说。
- 对 `manual_action_required` 必须给用户可点的 URL。
- 对 `failed` / `not_found` 给明确原因（`evidence` / `reason`）。
