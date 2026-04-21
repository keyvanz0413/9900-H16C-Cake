# Orchestrator Flow

## 总览

`IntentLayerOrchestrator.input(user_message)` 是 `email-agent` 对外的唯一入口。每一次 HTTP/CLI 消息都会走完下面这条流水线：

```
user_message
    │
    ▼
┌───────────────┐   no_execution_confidence >= 9.0
│ Intent Agent  │─────────────► direct response
└───────┬───────┘
        │否
        ▼
┌───────────────┐
│ Planner Agent │──► [{id, type, name, goal, reads}, ...]
└───────┬───────┘
        │
        ▼  对每个 step 顺序执行
┌──────────────────┐        ┌──────────────────┐
│ Skill Input      │        │ Main Agent Step  │
│ Resolver Agent   │        │ (type == agent)  │
└────────┬─────────┘        └────────┬─────────┘
         ▼                            ▼
┌──────────────────┐        ┌──────────────────┐
│ PythonSkill      │        │ main_agent       │
│ Executor         │        │ (tools, re_act)  │
└────────┬─────────┘        └────────┬─────────┘
         └────────────┬───────────────┘
                      ▼
             StepExecutionResult
                      │
                      ▼
             ┌─────────────────┐
             │ Finalizer Agent │──► user reply
             └─────────────────┘
                      │
                      ▼
             MarkdownMemoryStore.apply_update()
```

---

## 关键阶段与代码入口

| 阶段 | 方法 | Agent |
|---|---|---|
| Intent | `_analyze_intent()` | `intent_agent` |
| Plan | `_plan_execution()` | `planner_agent` |
| Resolve | `_resolve_skill_arguments()` | `skill_input_resolver_agent` |
| Skill Exec | `_execute_skill_step()` | `PythonSkillExecutor` 加载 `skills/<name>.py` |
| Agent Exec | `_execute_agent_step()` | `main_agent` |
| Final | `_finalize_execution()` | `finalizer_agent` |
| Memory | `MarkdownMemoryStore.apply_update()` | `user_memory_writer_agent` / `writing_style_writer_agent` |

---

## 会话与对话窗口

- **`current_session`**：ConnectOnion 提供的 dict，贯穿一次请求；用于 `pending_tool`、审批标记（`calendar_approve_all`、`calendar_approved_tools`）、`trace`。
- **Dialogue Store**：orchestrator 维护的一个列表，每条为 `DialogueItem(role, content)`。Intent 与 Finalizer 阶段通过 `split_context` 切成 40+10。
- **Session 传递**：前端 `oo-chat` 会在 `/input` 请求中携带上一轮返回的 `session`；orchestrator 用它还原对话。

---

## 失败语义

| 阶段失败 | 行为 |
|---|---|
| Intent JSON 解析失败 | 回退为"走 Planner"并记录 warning |
| Planner 返回空 `steps` | 直接进入 Finalizer，由它回复"没有动作" |
| Resolver 校验失败 | 当前 step 记 `failed`，Planner 不重试，由 Finalizer 解释 |
| Skill 内部抛异常 | `execute_skill()` catch，转为 `StepExecutionResult(status=failed)` |
| Main Agent 输出非法 JSON | 记 `failed`，`reason` 带解析错误 |
| Finalizer 失败 | orchestrator 兜底一个"系统故障"模板回复 |

---

## 兼容回退

`_run_compatibility_flow()` 保留了旧的 "skills_selector" 提示（`prompts/skills_selector.md`）作为回退——当没有 `planner_agent` 可用（模型未配置）时仍可运行最少功能。它只支持单技能路径，不支持 `type: agent` 步骤。新部署应确保 `planner_agent` 正常配置。

---

## 记忆回写时机

- **`user_update_summary`**（来自 Intent）+ **finalizer 产出的对话结论**共同组成 `MemoryUpdate`。
- `apply_update()` 只在 Finalizer 成功后调用；失败路径不会污染记忆文件。
- 写入由子 Agent 负责，详见 [memory-store.md](memory-store.md)。

---

## 可观测性

- `print(...)`：关键阶段（Planner 产出、技能调用前后）会打 `[skill:name] ...` 日志到 stdout。
- `trace`：`current_session["trace"]` 记录每一次 tool 的 `tool_call` / `tool_result`，供 `gmail_sync_plugin` 等钩子消费。
- 前端：`oo-chat` 通过 `/input` 返回的 `session.trace` 渲染逐步过程。
