# Skill Input Resolver

## 职责

Planner 只说"用哪个技能、做什么目标"，不填参数。Skill Input Resolver 负责把 **自然语言目标 + 上游 step 结果** 映射为 **符合 `input_schema` 的参数字典**。

代码位置：`IntentLayerOrchestrator._resolve_skill_arguments()`，使用独立的 `skill_input_resolver_agent`。
提示词：`email-agent/prompts/skill_input_resolver.md`。

---

## 输入

注入提示的上下文片段：

1. 当前 step 的 `name`、`goal`、`reads`。
2. 从 `registry.yaml` 读出的 `input_schema`（字段、类型、是否必填、默认值、描述）。
3. 已执行的 `reads` step 的 `artifact` 序列化结果（`serialize_step_result`）。
4. 本轮用户最新消息（用来补齐自然语言意图）。

---

## 输出契约（JSON）

```json
{
  "arguments": { "days": 7, "max_results": 200 },
  "reason": "用户让总结最近一周"
}
```

- `arguments` 必须满足 `input_schema`：
  - 类型：`int` / `float` / `str` / `bool`
  - 必填项不可缺省
  - 未声明的字段会被 `validate_skill_arguments()` 丢弃
- `reason` 仅用于调试日志，不会回传给用户。

---

## 参数校验

`validate_skill_arguments(arguments, input_schema)` 位于 `intent_layer.py`：

- **类型强制转换**：能转则转（`"7"` → `7`），不能则抛异常。
- **必填检查**：缺项直接 raise，上抛给 `_execute_skill_step` 捕获并记为 step 失败。
- **未声明字段剔除**：避免把无关上下文漏进技能内部。
- **默认值填充**：`input_schema` 中给了 `default` 就补上。

校验失败时返回结构化错误，Planner 不会自动重试；由 Finalizer 决定如何向用户解释。

---

## 典型示例

### `weekly_email_summary`

schema:
```yaml
input_schema:
  days:
    type: int
    default: 7
    required: false
  max_results:
    type: int
    default: 200
    required: false
```

解析示例：

| 用户/goal | 解析结果 |
|---|---|
| "帮我看一下这周邮件" | `{"days": 7, "max_results": 200}` |
| "最近三天就行" | `{"days": 3, "max_results": 200}` |
| "扫一周，但别太多，100 封够了" | `{"days": 7, "max_results": 100}` |

### `send_prepared_email`

schema 要求 `to` / `subject` / `body` 必填。Resolver 必须从 `reads` 的上游 artifact（通常是 draft step）里抽出 `to`、`subject`、`body`，否则抛必填缺失错误。

---

## 与 Planner 的边界

| 职责 | Planner | Input Resolver |
|---|---|---|
| 决定是否执行 | ✅ | ❌ |
| 决定执行顺序 | ✅ | ❌ |
| 填具体参数 | ❌ | ✅ |
| 从上游结果抽值 | ❌（只做 `reads` 声明） | ✅（真正读 artifact） |

保持这个边界是"计划/执行解耦"的核心。Planner 稳定，Input Resolver 容错；加新技能只需改 `registry.yaml`，不用动 Planner 提示词。
