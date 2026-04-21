# Planner

## 职责

Planner 把用户请求拆成一份 **串行执行计划**。它不执行任何工具，只产出下一步让谁做、怎么做、依赖哪些上游步骤的结果。

代码位置：`email-agent/intent_layer.py` 中 `IntentLayerOrchestrator._plan_execution()`，调用独立的 `planner_agent`。
提示词：`email-agent/prompts/planner.md`。

---

## 为什么是"串行"

- Agent 侧状态（Gmail 草稿、日历事件、记忆文件）对并发写敏感，串行更安全。
- 下游步骤经常要读前一步的 `artifact`（例如"先搜到 id 再发件"），并发会导致形参缺失。
- 调试：trace 天然线性，易于 Finalizer 聚合与前端渲染。

---

## 输出契约（JSON）

```json
{
  "reason": "为什么选这条路径",
  "steps": [
    {
      "id": "s1",
      "type": "skill | agent",
      "name": "weekly_email_summary | draft_reply_from_email_context | ...",
      "goal": "一句话说明这一步要达成什么",
      "reads": []
    },
    {
      "id": "s2",
      "type": "agent",
      "name": "main",
      "goal": "根据 s1 的 artifact 起草回复",
      "reads": ["s1"]
    }
  ]
}
```

字段语义：

| 字段 | 说明 |
|---|---|
| `id` | 当前计划内唯一，用于 `reads` 引用 |
| `type` | `skill` 指向 `registry.yaml` 中的技能；`agent` 指向通用 Agent 一步式执行 |
| `name` | 技能名或 `main`；`agent` 类型只允许 `main` |
| `goal` | 自然语言目标，用于 Skill Input Resolver / main-agent 上下文 |
| `reads` | 声明依赖的上游 step id，执行器据此把 artifact 注入上下文 |

---

## 两种 step 类型的分工

| 类型 | 用途 | 执行器 |
|---|---|---|
| `skill` | 已登记的标准化流水线，工具调用固定、参数严格 | `PythonSkillExecutor.run()` 加载 `skills/<name>.py` 并调用 `execute_skill()` |
| `agent` | 开放式操作（一次发件、一次日历创建、一次自由问答） | `IntentLayerOrchestrator._execute_agent_step()` 走 `main_agent` |

选 `skill` 的信号：目标可以被一个登记技能完整覆盖。
选 `agent` 的信号：目标需要灵活组合多种工具，或仅需一次具体写操作。

---

## 依赖的表达

- `reads` 只接受已出现在当前 `steps` 内且序号更小的 id。
- 执行器会把被 `reads` 的 step 的 `artifact` 序列化为 JSON 片段注入下一步上下文（`serialize_step_result`）。
- Planner 不自己解析前序结果，只声明依赖。解析在下游（Skill Input Resolver / main-agent 提示）里完成。

---

## 常见模式

### 单技能直发

```json
{"steps":[{"id":"s1","type":"skill","name":"weekly_email_summary","goal":"总结本周邮件","reads":[]}]}
```

### 先搜后写（发件）

```json
{"steps":[
  {"id":"s1","type":"skill","name":"draft_reply_from_email_context","goal":"基于最近未回复邮件起草回复","reads":[]},
  {"id":"s2","type":"skill","name":"send_prepared_email","goal":"把 s1 草稿发出","reads":["s1"]}
]}
```

### 混合 skill + agent

```json
{"steps":[
  {"id":"s1","type":"skill","name":"urgent_email_triage","goal":"拉出紧急邮件","reads":[]},
  {"id":"s2","type":"agent","name":"main","goal":"针对其中的会议冲突创建日历事件","reads":["s1"]}
]}
```

---

## 边界与常见陷阱

- **不要把 Finalizer 当成一步**：Finalizer 在整个 plan 执行完之后自动运行，不应出现在 `steps` 中。
- **不要跨对话轮复用 step id**：每一轮 Planner 重新生成。
- **没有技能能覆盖时才用 agent**：通用 Agent 步骤更难追踪、更容易飘，能用 skill 就用 skill。
