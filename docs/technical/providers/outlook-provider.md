# Outlook Provider

## 组件

当 `has_outlook` 生效（且 `has_gmail` 为假）时，`email-agent/agent.py` 注入：

| 对象 | 来源 | 作用 |
|---|---|---|
| `Outlook()` | `connectonion.Outlook` | 收发件、搜索、草稿、签名 |
| `MicrosoftCalendar()` | `connectonion.MicrosoftCalendar` | 日历读写 |
| `system_prompt` | `prompts/outlook_agent.md` | 主 Agent 的 Outlook 场景提示 |

---

## 不注入的东西

Outlook 分支当前 **不挂** 以下组件：

- `build_gmail_sync_plugin(...)` —— 发件后 CRM 同步是 Gmail 专属。
- `calendar_approval_plugin` —— 日历审批只在 Gmail 链路里验证过。
- `extract_recent_attachment_texts` —— 附件文本抽取工具内部依赖 Gmail 实现。
- `get_unsubscribe_info` / `post_one_click_unsubscribe` —— Unsubscribe 工具目前只覆盖 Gmail。

结论：**订阅治理、CRM 自动同步、日历审批在 Outlook 上暂不可用**。用户可以发邮件、看邮件、开会议，但高级流程受限。

---

## ConnectOnion 版本容错

```python
try:
    from connectonion import Outlook, MicrosoftCalendar
except ImportError:
    tools.append(UnavailableEmailProvider("outlook"))
```

如果安装的 ConnectOnion 版本里没有 Outlook 子模块，agent 启动时会挂一个 stub provider：任何方法被调用都直接抛"Outlook support is unavailable"。这样 Intent/Finalizer 链路仍可跑，错误信息清晰。

---

## 身份获取

`Outlook` 对象也提供 `get_my_identity` / `detect_all_my_emails` 等接口。Token 由 `MICROSOFT_ACCESS_TOKEN` / `MICROSOFT_REFRESH_TOKEN` 经 ConnectOnion 管理。

---

## 与 Gmail 的语义差异（LLM 视角）

- 标签体系：Outlook 使用 folder + category，与 Gmail 的 labels 不是 1:1 映射。
- 搜索语法：`prompts/outlook_agent.md` 里给出适合 Outlook 的查询样例，不要套 Gmail 的 `in:inbox newer_than:Nd` 语法。
- 发件后副作用：没有 `gmail_sync_plugin`，所以 CRM `last_contact` 字段不会被自动更新；需要由 Skill 或 main agent 显式调用 `update_contact`。

---

## 路线图（信息性）

Outlook 功能补齐未在当前代码中实现；如要补齐，建议按下面的顺序：

1. 给 `Outlook` 补一个与 Gmail 等价的 `update_contact` 接口（或把 CRM 读写抽成一个独立 tool）。
2. 实现 Outlook 版 `extract_recent_attachment_texts`。
3. 让 `unsubscribe_tool` 的解析逻辑支持 Outlook 的 `List-Unsubscribe` 头读取（底层 MIME 头通用，主要是读头 API 差异）。
4. 把 `calendar_approval_plugin` 的 tool 名单扩到 `MicrosoftCalendar` 的写方法。

实现之前，本文档以"当前状态"为准。
