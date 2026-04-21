# Skill: `draft_reply_from_email_context`

## 目标

定位一封目标邮件，把它的元数据、正文、用户写作风格打包给 Finalizer，**由 Finalizer 写回信草稿**（技能本身不发件，也不 save draft）。

代码：`email-agent/skills/draft_reply_from_email_context.py`。

---

## 两种选择目标邮件的模式

`selection_mode` 由 Resolver 决定：

### 1. `unanswered_rank`（默认优先）

- 调 `get_unanswered_emails(within_days=7, max_results=30)`。
- 从输出按 `数字. From: ... / Subject: ... / Thread ID: ...` 结构解析出有序列表。
- 按 `target_rank`（1 起）挑一条。
- 再用 `search_emails` 以 `from:+subject:` 查询定位到具体 message id。
- 最后调 `get_email_body` 拉整封正文。

### 2. `search_query`

- 用户给出自然语言查询（例如 "Alice 上周发的 spec 邮件"）。
- `_build_search_query(query, days)`：若用户串里没有 `in:` / `newer_than:` 等 Gmail 语法，自动加 `in:inbox newer_than:Nd (...)` 包裹。
- 拿第一条 id 的正文。

Resolver 不确定时默认 `unanswered_rank` 且 `target_rank=1`。

---

## 读取写作风格

从 `skill_runtime.paths.writing_style_markdown` 或回退到仓库内 `email-agent/WRITING_STYLE.md`：

- 文件不存在 / 为空：注入占位 `No writing style profile yet.`
- 有内容：作为 `[WRITING_STYLE]` 段落注入 bundle。

Finalizer 根据这段风格画像生成回复的语气、结构、称呼、落款。

---

## Bundle 字段

```
[DRAFT_REPLY_FROM_EMAIL_CONTEXT_BUNDLE]
skill_name: draft_reply_from_email_context
selection_mode: unanswered_rank | search_query
target_rank: N
search_days: N
unanswered_within_days: 7
unanswered_max_results: 30
mode_status: target_found | no_search_match | rank_out_of_range | lookup_failed | invalid_selection_mode | missing_query
target_email_id: ...

[WORKFLOW_REASON] ...
[WRITING_STYLE] ...
[SEARCH_RESULTS] ...
[SEARCH_MATCHED_EMAIL_IDS] ...
[UNANSWERED_RESULTS] ...
[SELECTED_UNANSWERED_ENTRY] ...
[UNANSWERED_LOOKUP_SEARCH] ...
[TARGET_EMAIL_BODY] ...
```

`notes` 中包含硬约束（"绝不声称已发送"、"只能以 target 邮件为依据"、"模仿用户风格"）。

---

## Finalizer 期望

- 输出一份 **完整可发送的回复草稿**：收件人（from of target）、主题（Re: ...）、正文（签名按 WRITING_STYLE）。
- 只基于 target 邮件事实；不编造未提及的项目、截止日期。
- 明确标注"这是草稿，尚未发送"。
- 若状态非 `target_found`：按状态码说明原因并停止拟稿。

---

## 后续链路

常见组合：

```
s1 draft_reply_from_email_context
s2 send_prepared_email  (reads: [s1])
```

Planner 通常只在用户显式说"发出去"后才加入 `s2`；默认只到草稿为止。
