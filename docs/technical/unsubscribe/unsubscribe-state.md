# Unsubscribe State

## 概览

`email-agent/unsubscribe_state.py` 维护一份 **本地 JSON 文件**，记录已知 candidate 的生命周期：`active` 或 `hidden_locally_after_unsubscribe`。文件默认放在 `email-agent/UNSUBSCRIBE_STATE.json`。

---

## 状态取值

```python
ACTIVE_STATUS = "active"
HIDDEN_STATUS = "hidden_locally_after_unsubscribe"
```

- `active`：本地认为仍然可能出现在推荐退订列表里。
- `hidden_locally_after_unsubscribe`：用户通过 `unsubscribe_execute` 成功退订过，下一次 discovery 不再展示。

Normalizer（`_normalize_state_record`）会把任何其它 `status` 值回退为 `active`，避免非法状态污染文件。

---

## 文件路径解析

```python
runtime_value = skill_runtime.get("unsubscribe_state_path")   # 运行时注入，优先
env_value     = os.getenv("UNSUBSCRIBE_STATE_PATH")           # 其次
fallback      = <repo>/email-agent/UNSUBSCRIBE_STATE.json     # 最后
```

- `skill_runtime` 是 orchestrator 注入给技能的运行时字典；方便测试/多账户下把路径打到临时目录。
- `UNSUBSCRIBE_STATE_PATH` 便于容器部署时把文件挂载到持久卷。
- `Path(...).expanduser().resolve()`：支持 `~/...`。

---

## 记录结构

```json
{
  "version": 1,
  "items": [
    {
      "candidate_id": "newsletter.example.com:ab12cd34ef56",
      "sender": "Example Newsletter <newsletter@example.com>",
      "sender_email": "newsletter@example.com",
      "sender_domain": "example.com",
      "representative_email_id": "19xxx",
      "status": "active",
      "updated_at": "2026-04-21T05:03:00+00:00",
      "method": "one_click",
      "subjects": ["Weekly digest", "Special offer"],
      "sample_email_ids": ["19xxx", "18yyy"],
      "recent_count": 7
    }
  ]
}
```

字段要点：

- `candidate_id` —— 稳定主键，来自 `unsubscribe_workflow.candidate_id_for_sender`（`readable:sha1(email|domain)[:12]`）。
- `sender_email` / `sender_domain` —— 统一转小写。
- `subjects` / `sample_email_ids` —— 最多 5 条，只保留代表性的。
- `recent_count` —— 最近窗口看到多少封。每次 merge 时累加。
- `updated_at` —— UTC ISO8601（秒级，`microsecond=0`）。

---

## 对外 API

| 函数 | 用途 |
|---|---|
| `load_unsubscribe_state_records(skill_runtime=None)` | 读全部 records（规范化后） |
| `visible_unsubscribe_state_records(records)` | 过滤出 `active` 条目 |
| `hidden_unsubscribe_state_records(records)` | 过滤出 `hidden` 条目 |
| `index_unsubscribe_state_records(records)` | 生成 `{candidate_id: record}` 字典 |
| `merge_discovered_candidates(candidates, skill_runtime=None)` | 合并新发现的 candidate；既能 update 已有记录，也能 insert |
| `mark_candidates_hidden_after_unsubscribe(candidates, skill_runtime=None)` | 成功退订后打上 `hidden` 状态 |

返回对象都是 **深拷贝**（`copy.deepcopy`），避免外部改动误触内存缓存。

---

## `merge_discovered_candidates`

增量合并策略：

- **存在**：更新 `sender / sender_email / sender_domain / representative_email_id / method / subjects / sample_email_ids / recent_count`；保留 `status`（不因为又看到就把 hidden 翻回 active）。
- **新增**：写入一条新的 record，`status = active`，`updated_at = now`。
- 同时返回 `{inserted_count, updated_count, items}`，方便 discovery bundle 输出统计。

---

## `mark_candidates_hidden_after_unsubscribe`

- 必须只传 **执行成功** 的 candidate（见 [unsubscribe-execute 的 SUCCESSFUL_HIDE_STATUSES](../skills/unsubscribe-execute.md)）。
- 对每个 candidate 按 `candidate_id` 查 record；**没有就先创建**，随后打上 `hidden` 状态。
- `updated_at` 更新为当前 UTC 时间。

---

## 为什么要有本地状态

- Gmail 侧的订阅真实状态我们无法实时查询，`gmail_subscription_ui_status` 永远是 `not_updated_by_agent`。
- 如果每次都基于实时搜索结果推荐退订，用户退订过之后再次出现在推荐列表，会造成"为什么我又看到了"的困惑。
- 本地状态只做 **过滤**，不做 **权威**：真实订阅关系仍以发件方邮件流为准。
- 持久化到 JSON 文件使其可审计、可备份，也可被手动修复。

---

## 容错

- 文件不存在 / 损坏 → 返回默认 payload `{"version":1,"items":[]}`，不抛错。
- 写入失败（磁盘只读）→ 调用方（skill）选择是否忽略；`merge_discovered_candidates` 本身会把失败冒泡给调用者。
- 未来 schema 升级：预留 `version` 字段，迁移时可 hook。
