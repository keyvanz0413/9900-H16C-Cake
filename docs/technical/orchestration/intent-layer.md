# Intent Layer

## 职责

Intent Layer 是每一轮用户输入的 **第一站**。它只做两件事：

1. **判断意图**：区分闲聊 / 问候 / 澄清 / 可立即回答的问题 与 需要工具执行的请求。
2. **直答或放行**：置信度足够高时跳过所有下游阶段直接回复用户，否则把控制权交给 Planner。

代码入口：`email-agent/intent_layer.py`，由 `IntentLayerOrchestrator._analyze_intent()` 调用独立的 `intent_agent`。

---

## 输入窗口

Intent 阶段只看对话窗口，不看工具结果：

| 常量 | 值 | 含义 |
|---|---|---|
| `CONTEXT_WINDOW_LIMIT` | 50 | 总条目上限 |
| `OLDER_CONTEXT_LIMIT` | 40 | 靠前的历史上限 |
| `RECENT_CONTEXT_LIMIT` | 10 | 最近轮次上限 |

窗口由 `split_context()` 构造 `older + recent` 并拼接为系统提示的一部分。

---

## 输出契约（JSON）

`intent_agent` 必须严格返回 JSON：

```json
{
  "intent": "chitchat | question | clarification | task | ...",
  "no_execution_confidence": 0.0,
  "final_response": "如果要直接回答用户，这里放完整回复；否则空字符串",
  "reason": "给下游调试用的简短说明",
  "user_update_summary": "这一轮要回写入记忆的摘要（可空）"
}
```

解析容错由 `_extract_json_payload()` 负责：先剥 ```` ```json ```` 围栏，再 `raw_decode` 容忍尾随噪声。

---

## 直答阈值

```python
DIRECT_RESPONSE_THRESHOLD = 9.0
should_direct_respond = confidence >= 9.0 and bool(final_response)
```

- **`>= 9.0`**：闲聊、打招呼、对已回答过的内容做澄清，直接由 Intent 阶段回话，不进入 Planner。
- **`< 9.0`** 或 `final_response` 为空：进入 Planner 决定执行计划。

> 根目录 `INTENT_LAYER_PLAN.md` 使用 `> 8` 描述阈值，但运行代码以 `DIRECT_RESPONSE_THRESHOLD` 与 `>=` 比较为准。

---

## 记忆回写

Intent 结果中的 `user_update_summary` 会累加到当轮 `MemoryUpdate` 草稿；在 Finalizer 之后由 `MarkdownMemoryStore.apply_update()` 交给 `user_memory_writer_agent` 写入 `USER_PROFILE.md` / `USER_HABITS.md`。

---

## 提示词

`email-agent/prompts/intent_layer.md` 定义了：

- 四类意图分类与判断标准
- 置信度打分刻度（8 以下必须走 Planner）
- JSON 输出的字段定义与空值约定
- 对用户语言的回应策略（中文输入必须中文直答）

---

## 不做什么

- 不调用任何工具。
- 不读取工具执行历史 / trace。
- 不改写对话历史。
- 不负责写入记忆文件，只产出"建议写入的摘要"。
