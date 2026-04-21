# Main Agent Step

## 职责

当 Planner 选择 `type: agent` 时，这一步会交给 **通用 `main_agent`** 执行。它拥有完整的工具清单（Gmail/Outlook、日历、Shell、TodoList、WebFetch、Memory、Unsubscribe 等），负责没有被任何技能覆盖的开放式操作。

代码位置：`IntentLayerOrchestrator._execute_agent_step()`。
提示词：`email-agent/prompts/main_agent_step.md`。

---

## 输出契约（JSON）

`main_agent` 在 **每一步的末尾** 必须返回结构化 JSON，而不是自由文本：

```json
{
  "status": "success | partial | failed",
  "artifact": {
    "kind": "search_result | email_draft | event_created | memory_update | note | ...",
    "summary": "一句话概括这一步做了什么",
    "data": { "...": "结构化数据，可空" }
  },
  "reason": "为什么认为这一步到此结束"
}
```

| 字段 | 说明 |
|---|---|
| `status` | `success` = 目标达成；`partial` = 做了一部分；`failed` = 没能完成 |
| `artifact.kind` | 自由枚举，由 main_agent 按实际场景选择 |
| `artifact.summary` | 给 Finalizer / 下一步 `reads` 读的摘要 |
| `artifact.data` | 结构化载荷，下一步可按键取值 |
| `reason` | Debug 用 |

> 根目录 `MAIN_AGENT_STEP_JSON_OUTPUT.md` 是这份契约的原始设计稿。

---

## 为什么要强制 JSON

- Planner 的 `reads` 依赖是可寻址的：下一步想读 `to` 字段，必须知道它在 `artifact.data.to`。
- Finalizer 不跟工具对话，只跟 artifact 对话。自由文本无法可靠解析。
- 前端 `oo-chat` 需要区分"做了事"和"在说话"，JSON 让它能把每一步渲染成轨迹卡片。

---

## 工具调用策略

`main_agent` 可以在内部任意调用工具（`tools/`、Gmail、Calendar、Shell…）直到它认为目标达成，**只在最后**输出上面的 JSON。`re_act` 插件负责推理-动作循环；`before_each_tool` / `after_each_tool` 钩子负责审批与后置同步（见 [calendar-approval-plugin](../providers/calendar-approval-plugin.md) 与 [gmail-sync-plugin](../providers/gmail-sync-plugin.md)）。

---

## Grounding 规则摘要

提示词里的硬性约束（节选）：

- **不要编造邮件、事件、人名**：任何 `artifact.data` 中的字段必须来自真实工具返回。
- **写操作需要 `to` 或 `event_id`**：缺少就先搜再写，绝不瞎填。
- **被审批拦住**：`calendar_approval_plugin` 抛错时原样上报 `failed`，在 `reason` 中解释原因。
- **语言一致**：`summary` 与用户本轮语言保持一致，其他字段保留英文键值。

---

## 与技能的分工

| 场景 | 用 Skill | 用 Agent Step |
|---|---|---|
| 批量邮件总结 / 分类 | ✅ | ❌ |
| 根据最近邮件生成草稿 | ✅（`draft_reply_from_email_context`） | ❌ |
| 一次性发送一封指定邮件 | ✅（`send_prepared_email`） | ❌ |
| 创建一个日历事件 | ❌ | ✅ |
| 自由的 shell 查询 / 本地文件操作 | ❌ | ✅ |
| 解 unsubscribe 但要求自定义流程 | ❌ | ✅ |

判断标准：**能被一个登记技能完整覆盖 → skill；否则 → agent。**
