# Provider Switching

## 目标

同一份 `email-agent` 代码同时支持 **Gmail** 与 **Outlook**，但只激活一个（两个 provider 的方法签名存在重叠，不能同时挂到一个 Agent 上）。

代码位置：`email-agent/agent.py`。

---

## 判断逻辑

```python
def _provider_is_linked(flag_name: str, *token_env_names: str) -> bool:
    explicit_flag = os.getenv(flag_name)
    if explicit_flag is not None:
        return explicit_flag.strip().lower() == "true"
    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI"):
        return False
    return any(os.getenv(token_name) for token_name in token_env_names)
```

- 有显式标志 `LINKED_GMAIL` / `LINKED_OUTLOOK` → 听 flag。
- 否则在非测试 / 非 CI 环境，检查是否存在 `GOOGLE_*_TOKEN` 或 `MICROSOFT_*_TOKEN`。
- 测试与 CI 默认关闭，避免误连。

---

## 选择优先级

```python
if has_gmail:
    # Gmail + GoogleCalendar + GmailCompat mixin
elif has_outlook:
    # Outlook + MicrosoftCalendar
```

**Gmail 胜过 Outlook**：同时配置时，主分支总是走 Gmail，Outlook 分支被跳过。

---

## 注入差异

| 组件 | Gmail | Outlook |
|---|---|---|
| Email 工具类 | `GmailCompat(OpenAICompatibleGmailMixin, Gmail)` | `Outlook()` |
| 日历工具 | `GoogleCalendar()` | `MicrosoftCalendar()` |
| `system_prompt` | `prompts/gmail_agent.md` | `prompts/outlook_agent.md` |
| 专属插件 | `build_gmail_sync_plugin(...)` + `calendar_approval_plugin` | —（无） |
| 附件文本工具 | `extract_recent_attachment_texts` | 不注入 |
| Unsubscribe 工具 | `get_unsubscribe_info` + `post_one_click_unsubscribe` | 不注入 |

> Outlook 分支目前功能较浅：未挂发件后同步 CRM、未挂日历审批、未挂 unsubscribe 工具。所有订阅管理与 CRM 同步特性只在 Gmail 上完整可用。

---

## 两者都没有时

`tools` 保持为空，启动时打印：

```
⚠️  No email account connected. Use /link-gmail or /link-outlook to connect.
```

Agent 仍然可以启动（Memory / Shell / Todo / WebFetch 仍在），只是邮件工具不可用。

---

## OpenAI 工具 schema 兼容

`OpenAICompatibleGmailMixin`：

```python
class OpenAICompatibleGmailMixin:
    def bulk_update_contacts(self, updates: list[dict]) -> str:
        return super().bulk_update_contacts(updates)
```

ConnectOnion 原生 `Gmail.bulk_update_contacts` 的注解是 bare `list`，OpenAI tools schema 要求完整泛型（`list[dict]`）。Mixin 只重写签名，转调父类。`GmailCompat = (OpenAICompatibleGmailMixin, Gmail)` 组合后挂载到主 Agent。

Outlook 目前没有类似 mixin，因为它的方法签名与当前 OpenAI schema 无冲突。
