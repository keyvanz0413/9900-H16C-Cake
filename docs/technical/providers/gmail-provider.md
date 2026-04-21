# Gmail Provider

## 组件

Gmail 分支挂载的完整组件（`email-agent/agent.py` 中 `if has_gmail:` 段落）：

| 对象 | 来源 | 作用 |
|---|---|---|
| `GmailCompat(...)` | `connectonion.Gmail` + `OpenAICompatibleGmailMixin` | 收发件、搜索、标签、草稿、联系人 CRM |
| `GoogleCalendar()` | `connectonion` | 日历读写 |
| `build_gmail_sync_plugin(...)` | 本仓库 `plugins/gmail_sync_plugin.py` | 发件后更新 CRM `last_contact` |
| `calendar_approval_plugin` | 本仓库 `plugins/calendar_approval_plugin.py` | 日历写操作前的审批 |
| `extract_recent_attachment_texts` | `tools/attachment_text_tool.py` | 按查询批量抽取附件文本 |
| `get_unsubscribe_info` | `tools/unsubscribe_tool.py` | 统一退订元信息入口 |
| `post_one_click_unsubscribe` | 同上 | 执行 RFC 8058 一键退订 |
| `system_prompt` | `prompts/gmail_agent.md` | 主 Agent 的 Gmail 场景提示 |

这些对象只在 Gmail 链接成功时注入；Outlook 分支不会拿到。

---

## OpenAI Schema 兼容补丁

```python
class OpenAICompatibleGmailMixin:
    def bulk_update_contacts(self, updates: list[dict]) -> str:
        return super().bulk_update_contacts(updates)
```

ConnectOnion 的 `Gmail.bulk_update_contacts` 原始签名用了 bare `list`，OpenAI tool_call schema 会报"泛型参数缺失"。Mixin 只是把注解补全为 `list[dict]`，运行时委托父类。

使用方式：`class GmailCompat(OpenAICompatibleGmailMixin, Gmail): pass` 再 `GmailCompat()`。

---

## 身份获取

Gmail tool 自带 `get_my_identity`、`detect_all_my_emails`。Intent / Planner 通过这两个方法在系统提示中拼出"当前用户"身份。若 token 失效，`current_session` 里会落下错误，ICL 链路最终由 Finalizer 做出"需要重连 Gmail"的回复。

---

## 工具面向 LLM 的典型子集

工具数量多达几十个，常用于 skill / main agent：

- 读：`search_emails`、`get_email_body`、`get_email_attachments`、`get_sent_emails`、`get_unanswered_emails`、`list_labels`、`list_drafts`、`get_my_identity`
- 写：`send`、`reply`、`create_draft`、`update_label`、`archive`、`delete`、`mark_read`、`mark_unread`
- CRM：`get_all_contacts`、`update_contact`、`bulk_update_contacts`、`get_contact_notes`

完整清单以 `EMAIL_AGENT_TOOLS.md` 与 ConnectOnion 最新版本为准。

---

## 不做什么

- 不直接调 Gmail REST API；一切走 ConnectOnion 抽象。
- 不在代码里缓存 access token；由 ConnectOnion + OAuth 环境变量托管。
- 不为 Outlook 链路复用 Gmail 插件（sync / approval）。
