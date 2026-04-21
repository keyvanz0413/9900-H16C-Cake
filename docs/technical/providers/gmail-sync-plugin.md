# Gmail Sync Plugin

## 目标

每次用 `send` / `reply` 发件成功后，**自动更新对应联系人的 CRM `last_contact` 字段**。避免让每个 skill 自己手工调 `update_contact`，也避免 main agent 忘记更新。

代码：`email-agent/plugins/gmail_sync_plugin.py`。仅在 Gmail 分支被挂载。

---

## 触发时机

ConnectOnion 的 `after_each_tool` 钩子在任何工具执行完后触发。本插件只关心满足以下全部条件的 trace 条目：

```python
latest_trace.get("type") == "tool_result"
latest_trace.get("name") in {"send", "reply"}
latest_trace.get("status") == "success"
isinstance(args := latest_trace.get("args"), dict)
to := str(args.get("to") or "").strip()  # 非空
```

缺任一条件直接 `return`，不做任何事。

---

## 更新逻辑

```python
email_tool = email_tool_getter()
today = datetime.now().strftime("%Y-%m-%d")
result = email_tool.update_contact(to, last_contact=today, next_contact_date="")
```

- `email_tool_getter`：由 `agent.py` 里的 `_get_primary_email_tool` 提供，运行时解析到当前 Gmail 实例。
- `next_contact_date=""`：把已计划的下一次联系日期清空。语义："我刚联系过了，重置排期"。
- `update_contact` 返回的文本里如果包含 `"Updated"`，打印日志：
  ```
  [crm-sync] updated contact after send: <to>
  ```
- 其他返回 / 异常：
  - 异常被吞并打印 `[crm-sync] failed to update contact after send for <to>: <exc>`。
  - 插件 **不 raise**，以免打断 main agent 的正常对话流。

---

## 只认一个收件人？

`send` 工具的 `args.to` 可能是字符串（单一收件人）或逗号分隔的列表字符串。当前实现不拆分，而是直接把整段字符串传给 `update_contact`。ConnectOnion 的 `Gmail.update_contact` 自己会处理 `name <a@b>` / 多人列表解析。如果未来要改成精细的 per-recipient 更新，可以在这里加拆分逻辑。

---

## 与 `send_prepared_email` 的关系

`send_prepared_email` 技能显式调用 `send(...)`。它本身不做 CRM 同步；这一步由 `gmail_sync_plugin` 在 `after_each_tool` 中自动完成。

换句话说：

- 写技能只需要发邮件。
- 同步副作用由插件保证。
- Finalizer 给用户的回复里不需要自己提"已更新 CRM"——一般不值得向用户暴露这类后台事实。

---

## 只跑在 Gmail

Outlook 分支没有挂这个插件，也没有 `update_contact` 方法。等价的 CRM 同步目前在 Outlook 上不可用。
