# Unsubscribe Workflow (shared helpers)

## 目标

`email-agent/unsubscribe_workflow.py` 是 `unsubscribe_discovery` 与 `unsubscribe_execute` 两个技能的 **共享构件**：它不依赖 ConnectOnion / LLM，只是把"搜信箱 + 读退订头 + 归并到 per-sender candidate 列表"的纯逻辑抽出来。

---

## 常量

```python
DEFAULT_DAYS = 30
MAX_DAYS = 90
DEFAULT_MAX_RESULTS = 100
MAX_RESULTS_CAP = 250
METHOD_PRIORITY = {"one_click": 0, "mailto": 1, "website": 2, "unknown": 3}
```

两个技能对 `days` / `max_results` 均走 `clamp_int` 压到区间内。

---

## 核心函数

### 查询构造

```python
build_discovery_search_query(days)
  # in:inbox newer_than:Nd (unsubscribe OR newsletter OR subscription
  # OR "manage preferences" OR "email preferences" OR marketing)

build_targeted_search_query(target_query, days)
  # in:inbox newer_than:Nd ({target_query})
```

定向查询不加额外关键词，保持原意；discovery 查询涵盖常见订阅信号。

### search_emails 输出解析

```python
extract_email_ids(search_output)       # 只抽 "ID: <value>" 这一行
extract_search_entries(search_output)  # 结构化成 {from, subject, date, email_id}
```

`SEARCH_RESULT_FROM_PATTERN` 允许前缀 `1.` 或 `[INBOX]` 等装饰。

### 发件人 → candidate_id

```python
sender_parts(raw_from) -> (display, email, domain)
candidate_id_for_sender(sender_email, sender_domain)
  # readable + ":" + sha1(email|domain)[:12]
```

Readable 部分会被清洗为 `[a-zA-Z0-9_.@-]+`，最多 48 字符。这样即使人眼看到 id 也能大概认出来源。

### 方法归一 / 风险等级

```python
normalize_method("One-Click" | "ONECLICK" | ...) -> "one_click"
risk_level_for_method("one_click") -> "low"
risk_level_for_method("mailto"|"website") -> "medium"
risk_level_for_method("multiple") -> "review"
risk_level_for_method(other) -> "unknown"
```

### Evidence

`build_evidence(unsubscribe, item_error)` 把 `options` 里有哪些可用入口、tool 层是否报警、手动链接是否存在这些事实拼成 bullet 列表，放进 candidate 的 `evidence` 字段，Finalizer 可以直接引用。

### Candidate 合并

```python
merge_candidate(candidates_dict, candidate)
```

- 按 `candidate_id` 聚合同一发件人。
- `recent_count` 累加；`subjects`、`sample_email_ids` 去重最多 5。
- `method` 用 `_best_method`：按 `METHOD_PRIORITY` 取最低值（`one_click` 胜过 `mailto` 胜过 `website` 胜过 `unknown`）。切换时连带更新 `representative_email_id` / `unsubscribe` / `evidence`。

### 排序

```python
sort_candidates(list) -> list
```

排序键：`(METHOD_PRIORITY[method], -recent_count, sender_email)`。
→ 一键能退的排前、次数多的排前、同方法同次数按字母序。

---

## `collect_candidates`

两个技能都用这个函数做"实时发现"：

```python
collect_candidates(search_query, max_results, used_tools, log_prefix) -> dict
```

内部做四件事：

1. 调 `search_emails(query, max_results)` → `search_entries`。
2. 如果有 email id，再调 `get_unsubscribe_info(email_ids=[...])`；否则返回空 payload。
3. 按 id join：把每封邮件的 `unsubscribe` 元信息贴到对应 search entry 上。
4. `sender_parts` + `merge_candidate` 归并，最后 `sort_candidates` 返回有序列表。

返回结构（精简版）：

```python
{
  "search_query": "...",
  "search_kwargs": {...},
  "search_text": "...",
  "matched_email_ids": [...],
  "unsubscribe_kwargs": {...},
  "unsubscribe_text": "...",
  "ordered_candidates": [...],
  "inspected_count": N,
  "error_count": N,
}
```

---

## 目标查询匹配

```python
match_candidates_by_target_query(candidates, target_query) -> list
```

策略：

- 归一化 target（小写 + 连续空格折叠）。
- 逐个 candidate 把 `candidate_id / sender / sender_email / sender_domain / subjects[*]` 归一化做 fragments。
- **精确匹配** 优先；若没有精确，返回 **部分匹配**（一侧包含另一侧）。
- 没有任何匹配 → 空列表（`execute_skill` 据此判 `not_found`）。

匹配到多个候选时，`unsubscribe_execute` 视为歧义，不自动退订。

---

## 跨步读取：`extract_candidate_lists_from_read_results`

`execute` 可以通过 `reads` 拿到 discovery step 的 artifact。`extract_candidate_lists_from_read_results` 会从 read_results 的 `artifact.data.response`（discovery bundle 文本）里用正则切出 `[VISIBLE_CANDIDATES_JSON]` 或 `[VISIBLE_SUBSCRIPTIONS_AFTER_EXECUTION_JSON]` 段落并 `json.loads`。

好处：execute 不必再跑一遍发现流程，直接接上一步产出的 candidate 列表。

---

## 不做什么

- 不写文件（只读 state；写文件在 `unsubscribe_state.py`）。
- 不调 LLM；所有函数都是确定性纯函数。
- 不硬编码 Gmail；它只假设 `used_tools` 提供 `search_emails` 和 `get_unsubscribe_info` 两个 key。
