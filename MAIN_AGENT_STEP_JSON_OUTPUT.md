# Main Agent Step JSON 输出方案

这份文档定义一个最小实验方案：

- 不修改原有 [gmail_agent.md](/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/prompts/gmail_agent.md)
- 新建一个专门给主 agent step 使用的 prompt
- 让主 agent 不再直接输出最终用户自然语言
- 而是输出严格 JSON 的 `step_result`
- 最后继续交给现有 finalizer 统一汇总成 `final_response`

---

## 1. 背景

当前系统里，主 agent step 还是直接输出自然语言。

这意味着：

- `skill step` 更像中间结果
- `agent step` 更像最终回复

这两种输出形式不统一。

如果后续要稳定接入统一的 finalizer，那么主 agent 也应该输出结构化 step 结果，而不是直接面向用户说最终话。

---

## 2. 当前代码中的等价位置

早期讨论里说的是 `_run_main_agent()`。

但当前代码已经进入串行 planner 结构，实际等价位置是：

- [intent_layer.py](/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/intent_layer.py:1428) 的 `_execute_agent_step()`

所以本次最小代码改动，不是去改不存在的 `_run_main_agent()`，而是改当前真实入口 `_execute_agent_step()`。

---

## 3. 新 prompt 文件

新增：

- [main_agent_step.md](/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/prompts/main_agent_step.md)

它的职责是：

- 主 agent 仍然可以调用全量工具
- 仍然完成当前 step 的 `goal`
- 但不能直接输出用户最终回复
- 必须输出严格 JSON

---

## 4. 主 agent step 输出契约

主 agent step 必须输出：

```json
{
  "status": "completed",
  "artifact": {
    "kind": "agent_result",
    "summary": "string",
    "data": {}
  },
  "reason": "string"
}
```

### 字段说明

#### `status`

- 当前 agent step 的执行状态
- 当前最小方案至少支持：
  - `completed`
  - `failed`

#### `artifact`

- 主 agent 产出的中间结果
- 不再是最终用户回复

建议固定包含：

- `kind`
- `summary`
- `data`

#### `reason`

- 对当前 step 结果的简短说明
- 用于日志与调试

---

## 5. 最小代码改动

最小实现分两步：

1. 新建 prompt 文件，不动原始 prompt
2. 让 `_execute_agent_step()` 从：
   - 直接接收字符串
   - 直接包装成 `artifact.response`

改成：

- 解析 JSON
- 校验 `status / artifact / reason`
- 返回结构化的 `StepExecutionResult`

---

## 6. 为什么这版足够做实验

这版不要求一次性重构整个系统。

它只做一件关键事：

- 把主 agent 从“最终回复者”改成“step 执行器”

这样后面的 finalizer 读取所有 step 结果时：

- `skill step`
- `agent step`

就都属于统一的中间结果流。

---

## 7. 与现有 finalizer 的关系

当前 finalizer 已经读取：

- `intent`
- `older_context`
- `recent_context`
- `all_step_results`

所以只要主 agent step 也输出结构化 step 结果，
现有 finalizer 就可以继续统一汇总，而不需要先改 finalizer 逻辑。

---

## 8. 一句话总结

这个实验方案的核心是：

- 不改原始主 agent prompt
- 新建一个 `main_agent_step` prompt
- 让主 agent step 输出严格 JSON 的 `step_result`
- 再继续交给最终 finalizer 做统一输出
