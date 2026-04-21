# Finalizer

## 职责

Finalizer 是 **唯一面向用户发声** 的 LLM 阶段。它接收 Planner 产出的所有 step 结果，把它们聚合、润色、用用户的语言写一份最终回复。

代码位置：`IntentLayerOrchestrator._finalize_execution()`，独立 `finalizer_agent`。
提示词：`email-agent/prompts/finalizer.md`。

---

## 输入

Finalizer 的上下文由以下内容拼接而成：

1. 用户本轮最新消息
2. Intent 阶段的 `reason` / `user_update_summary`
3. Planner 产出的 `steps` 与 `reason`
4. 每个 step 的 `StepExecutionResult`（含 `artifact` 与 `status`）
5. 必要时的对话窗口（与 Intent 阶段相同的 50/40/10 分配）

---

## 硬性约束

- **不能调用任何工具**。Finalizer 的 Agent 实例没有注册 tool_set。
- **不能扩展 skill 的作用域**。如果用户问的内容超出已有 artifact，只能说"这一轮没查这个"，不得凭空补写。
- **不能编造字段**。所有邮件、事件、发件人、时间均来自 `artifact.data`。
- **语言跟随用户**：用户中文 → 中文回复；英文 → 英文回复。
- **输出契约**：直接给自然语言，不再包 JSON 层。

---

## 聚合策略

提示词要求 Finalizer：

1. 先判断 **整体成败**：只要关键 step 失败，要在回复最前面点明，再解释为什么。
2. 对数据密集的 artifact（如周总结、紧急邮件、Bug 邮件）输出 **有序清单 + 简短说明**。
3. 对写操作（发件、建事件）用 **一句话确认 + 要点**，不要把 artifact 原样吐出。
4. 对失败/被审批拦截的 step 要 **告诉用户下一步怎么办**，而不是报错码。

---

## 技能自带 Finalizer 提示

部分技能（见 `skills/*.py`）会在 `response` 字段里自带 **finalizer instruction**。例如：

- `bug_issue_triage.py`：要求 Finalizer 按优先级排序。
- `urgent_email_triage.py`：要求生产事故类内容优先。
- `weekly_email_summary.py`：要求按类别（通知 / 待回复 / 订阅）分组。

这些指令会随 artifact 一起进入 Finalizer 上下文，Finalizer 应当遵守。

---

## 与 Intent 直答的区别

| 场景 | 谁回复 |
|---|---|
| 用户问"你好" | Intent（`no_execution_confidence >= 9.0`） |
| 用户问"你能做什么" | Intent |
| 用户让总结邮件 | Finalizer（在 skill 执行完之后） |
| 用户让发件 | Finalizer（在 send skill 成功后） |
| 意图不明 / 需澄清 | Intent 或 Finalizer 视置信度决定 |

Intent 直答时整条 plan 不会被构建，Finalizer 也不会被调用。

---

## 失败路径

- **某个 step 失败**：Finalizer 收到 `status="failed"` 的 artifact，需显式告知用户并给出后续建议（如"请重试"、"请确认收件人"）。
- **所有 step 都失败**：Finalizer 依旧要产出回复，不能抛异常回传给前端。
- **Plan 为空**：一般意味着 Planner 认为没必要执行；Finalizer 会按"无动作"语气回复。

---

## 不做什么

- 不改 artifact；不改记忆；不写文件。
- 不决定 user_update_summary；那在 Intent 阶段。
- 不打断工具流程；它只在工具流程全部结束后跑一次。
