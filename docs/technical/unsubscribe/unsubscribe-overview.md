# Unsubscribe Subsystem Overview

一套跨 **tool / workflow / state / skills** 四层的订阅治理方案，目标是让用户以最低风险、可审计地管理大批订阅邮件。

```
┌─────────────────────────┐       ┌─────────────────────────┐
│ unsubscribe_discovery   │       │ unsubscribe_execute     │
│  (skill)                │       │  (skill)                │
└──────────┬──────────────┘       └────────────┬────────────┘
           │ uses                              │ uses
           ▼                                   ▼
┌─────────────────────────────────────────────────────────┐
│ unsubscribe_workflow.py                                  │
│  • build_discovery_search_query / build_targeted_search  │
│  • collect_candidates (search + get_unsubscribe_info)    │
│  • merge_candidate / sort_candidates                     │
│  • match_candidates_by_target_query                      │
│  • extract_candidate_lists_from_read_results             │
└──────────┬───────────────────────┬──────────────────────┘
           │                       │
           ▼                       ▼
┌──────────────────────┐    ┌──────────────────────────┐
│ tools/               │    │ unsubscribe_state.py     │
│ unsubscribe_tool.py  │    │ UNSUBSCRIBE_STATE.json   │
│  get_unsubscribe_info│    │  active / hidden_... 状态 │
│  post_one_click_...  │    │  merge / filter / mark   │
└──────────────────────┘    └──────────────────────────┘
```

---

## 四层边界

| 层 | 关心什么 | 不关心什么 |
|---|---|---|
| Tool | 单封邮件 → 单一退订元信息 JSON；单个 POST | 候选人级去重、状态持久化 |
| Workflow | 一组邮件 → 合并成 per-sender candidate 列表 | LLM / 提示 |
| State | 本地 candidate 的生命周期（active / hidden） | Gmail 状态 |
| Skill | 用户意图 → 选用上述三层完成一次操作 | 工具内部细节 |

这让每层可以独立演进：换 tool 实现不影响 workflow；换 state 路径不影响 skill。

---

## 关键不变量

- **一切写操作必须显式触发**：discovery 永远只读；execute 必须拿到 `target_queries` 或 `candidate_ids` 至少一项。
- **绝不打开网站**：website 方法仅提供 manual_unsubscribe 链接，由用户自行点击。
- **成功才 hide**：只有 `post_one_click_unsubscribe` 或 mailto `send` 被确认成功的条目才会被标记 `hidden_locally_after_unsubscribe`。
- **live + local 结合**：每次 discovery 都重新扫信箱，再与本地状态合并/过滤；本地状态只起"过滤"作用，不代替 Gmail 真实订阅关系。

---

## 五类执行结果

`unsubscribe_execute` 把每个目标归入其中一类：

| 类别 | 含义 |
|---|---|
| `newly_unsubscribed` | 本次成功（one_click / mailto 发出） |
| `already_unsubscribed` | 本地状态已是 hidden |
| `manual_action_required` | 只能给 URL 让用户点 |
| `failed` | 尝试执行但未成功 |
| `not_found` | 无法解析到 candidate（目标模糊 / 实时搜索命中多个或零个） |

Finalizer 必须按类别分组向用户汇报，避免把失败说成成功。

---

## 方法风险等级

| method | risk_level | 说明 |
|---|---|---|
| `one_click` | `low` | RFC 8058，一个 POST 请求，原子 |
| `mailto` / `website` | `medium` | 发件或跳链接，结果依赖发件人 |
| `multiple` | `review` | 邮件同时给了多个方式，需要人判断 |
| `unknown` | `unknown` | 头/正文没给机器可读信息 |

Finalizer 在呈现 discovery 结果时推荐标注风险等级。

---

## 详见子文档

- [unsubscribe-tool.md](unsubscribe-tool.md) —— 底层工具契约（JSON schema、POST 合规）
- [unsubscribe-state.md](unsubscribe-state.md) —— 状态文件结构
- [unsubscribe-workflow.md](unsubscribe-workflow.md) —— 跨层共享的纯函数

用户侧：

- [skills/unsubscribe-discovery.md](../skills/unsubscribe-discovery.md)
- [skills/unsubscribe-execute.md](../skills/unsubscribe-execute.md)
