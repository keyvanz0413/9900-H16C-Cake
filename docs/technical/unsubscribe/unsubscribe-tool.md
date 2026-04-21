# Unsubscribe Tool (`get_unsubscribe_info` / `post_one_click_unsubscribe`)

## 组件

`email-agent/tools/unsubscribe_tool.py` 只暴露两个面向 LLM 的工具：

1. `get_unsubscribe_info(email_ids, max_manual_links=5)` —— 读 `List-Unsubscribe` 头 + 正文，返回统一 JSON。
2. `post_one_click_unsubscribe(url, timeout_seconds=10)` —— 按 RFC 8058 发一次合规 POST。

这两个工具取代了早期设计里的 4 个细粒度工具（参见根目录 `UNSUBSCRIBE_TOOL_MERGE_PLAN.md`），避免 LLM 在"读头 / 解析正文 / 发 mailto / POST"之间拼装流程。

---

## `get_unsubscribe_info` 输出

```json
{
  "items": [
    {
      "email_id": "<gmail-message-id>",
      "unsubscribe": {
        "method": "one_click | mailto | website | unknown",
        "options": {
          "one_click": {
            "url": "https://...",
            "request_payload": { "url": "https://..." }
          },
          "mailto": {
            "url": "mailto:list-unsub@host?subject=Unsubscribe",
            "send_payload": { "to": "...", "subject": "...", "body": "..." }
          },
          "website": {
            "url": "https://...",                              // 从头解析
            "manual_links": [
              { "url": "https://...", "label": "Unsubscribe", "source": "email_body" }
            ]
          }
        }
      },
      "error": ""
    }
  ],
  "summary": {
    "requested_count": N,
    "analyzed_count": N,
    "error_count": N
  },
  "error": ""
}
```

### 关键字段

- **`method`** —— 基于优先级得出："能一键就一键；否则 mailto；否则 website；都不行 unknown"。
- **`request_payload`** —— `post_one_click_unsubscribe` 能直接接过去的参数。**LLM 不该自己拼 URL**，调用它即可。
- **`send_payload`** —— 从 `mailto:` URL 中预解析好的 `to / subject / body`，直接喂 `send`。
- **`manual_links`** —— 在没有机器可读方式时，从正文里扫到的人工退订链接；附 `label` 与 `source`。

---

## 读取策略

优先顺序：

1. 先通过 Gmail `users.messages.get` 以 `format=metadata` 拉 `List-Unsubscribe` 与 `List-Unsubscribe-Post` 头。
2. 用正则解析尖括号值，分出 `https://...` 与 `mailto:...`。
3. 如果 `List-Unsubscribe-Post` 含 `List-Unsubscribe=One-Click`，则头里的第一个 https 成为 one-click URL。
4. 如果既不支持 one-click 也没有 mailto，**才**去抓正文 HTML 扫 `<a>` + `unsubscribe|opt out|manage preferences` 正则，补 `website.manual_links`。

只在确有必要时下载正文，节约 Gmail API 配额。

---

## `post_one_click_unsubscribe`

### 合规性

- **只允许 HTTPS**：否则直接返回 `{"status":"failed","error":"invalid_url"}`。
- **POST body**：`List-Unsubscribe=One-Click`（urlencoded），`Content-Type: application/x-www-form-urlencoded`。
- **自定义 UA**：`User-Agent: email-agent unsubscribe client`。
- **超时**：由 `timeout_seconds` 控制，clamp 到 `[1, 30]`，默认 10。

### 状态映射

| HTTP | `status` |
|---|---|
| 200 / 204 | `confirmed` |
| 202 | `request_accepted` |
| 2xx 其他 | `request_submitted` |
| 非 2xx / 异常 | `uncertain` / `failed` |

### 输出

```json
{
  "status": "...",
  "http_status": 200,
  "url": "https://...",
  "evidence": "HTTP 200 response received. Response preview: ...",
  "sender_unsubscribe_status": "...",
  "gmail_subscription_ui_status": "not_updated_by_agent",
  "error": ""
}
```

`gmail_subscription_ui_status` 始终为 `not_updated_by_agent`：我们不点 Gmail 侧的"取消订阅"按钮，只走合规 POST。Gmail UI 上仍可能继续显示订阅按钮，直到 Google 侧刷新。

---

## 错误分支

- 空 / 非法 `email_ids` → `summary.error_count = 1`，`items = []`，顶层 `error` 填写原因。
- 邮件无相关头 → `method = unknown`，`options = {}`，`error = ""`（这不是异常，而是"没有可退订信号"）。
- 邮件读取失败（权限 / 404）→ 当条 `error` 字段写入原因，`error_count += 1`；不抛异常。

---

## 工具注入

```python
get_unsubscribe_info = build_get_unsubscribe_info_tool(_get_primary_email_tool)
```

`build_get_unsubscribe_info_tool` 绑定"当前 Gmail 实例获取器"，并把返回的闭包改名为 `get_unsubscribe_info` 以满足 LLM tool schema。Outlook 分支不注入。

---

## 不做什么

- 不打开浏览器 / 不跑 headless。
- 不跟踪退订是否"真的生效"；我们只能给 `status` 指示当前 POST 的 HTTP 结果。
- 不自动重试：失败由 skill / main agent 决定是否 retry。
- 不自己改 `UNSUBSCRIBE_STATE.json`；状态变更由 skill / `mark_candidates_hidden_after_unsubscribe` 负责。
