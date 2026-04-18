# Skill Finalizer 执行规范

这份文档只定义一件事：

- 当系统已经走到 `skill` 路径并且 skill 已经执行完后
- 在真正把结果返回给用户之前
- 再接一个无工具的 LLM
- 由它负责产出最终的 `final_response`

这份文档和 Intent Layer、Skills Selector、主 agent 的其它设计解耦。
这里只关心 `skill 后的那个 LLM` 应该怎么工作。

---

## 1. 目标

加这一层的目的不是再做一次执行，也不是再做一次路由，而是解决下面这个问题：

- skill 返回什么，现在系统就可能直接把什么发给用户
- skill 的输出可能太像“内部结果”，不够像最终用户回复
- 不同 skill 的输出风格可能不一致
- 如果让 skill 自己既负责执行又负责润色，就更容易越界脑补

所以这里新增一层：

```text
selected skill
-> skill execute
-> skill finalizer llm
-> final_response
```

这一层只负责：

- 读取 skill 已经产出的结果
- 结合已经确定好的 intent
- 结合最近少量上下文
- 生成最终给用户看的自然语言回复

这一层不负责：

- 选 skill
- 调工具
- 做外部查询
- 新增事实
- 擅自扩展 skill 能力边界

---

## 2. 触发时机

只有在下面条件同时满足时，才调用 Skill Finalizer：

1. 第二层已经选中了某个 skill
2. skill executor 已经实际执行
3. skill executor 返回 `completed = true`
4. skill executor 已经给出了可用的 `skill_result`

如果任一条件不满足，就不要调用这一层，直接按原有逻辑回退。

---

## 3. 定位

Skill Finalizer 的定位是：

- 一个单独的 LLM 调用
- 一个“表达整理层”
- 一个“最终回复生成层”

它不是：

- 执行器
- 推理链协调器
- 二次决策器
- 二次规划器

可以把它理解为：

- skill executor 负责“把事情做出来”
- skill finalizer 负责“把结果说给用户听”

---

## 4. 输入

这一层输入必须尽量小，只给它真正需要的内容。

### 固定输入

1. `intent`
2. `recent_context`
3. `selected_skill`
4. `skill_result`

### 不输入的内容

以下内容不要传给这一层：

- 当前用户原始消息
- older_context
- 全量历史对话
- 工具列表
- 工具 schema
- 系统执行 trace
- 主 agent prompt

原因是：

- `intent` 已经是上游压缩过的“当前用户要干什么”
- `recent_context` 足够帮助这一层理解最近对话语境
- 这一层不是拿来重新理解全局上下文的
- 输入太多会让它重新发散

---

## 5. 输入字段定义

### 5.1 `intent`

来源：

- 上游 Intent Layer 的输出

要求：

- 用一句话总结用户当前要干什么
- 这里是这一层理解任务的主依据

示例：

```text
The user wants a concise draft reply to a client email.
```

### 5.2 `recent_context`

来源：

- 最近最多 10 条自然语言对话项

要求：

- 只包含用户消息和 assistant 的自然语言回复
- 不包含工具调用日志
- 不包含工具原始结果
- 不包含系统 prompt

格式建议：

```text
[RECENT_CONTEXT]
User: 帮我给客户起草一封回复
Assistant: 我已经根据上下文起草好了草稿，下面是建议内容……
User: 可以，给我一个更简洁版本
```

这一段的作用是：

- 让 finalizer 知道最近语境
- 让它知道用户刚刚是不是在要求更简洁、更正式、更口语化
- 让它处理像“好的”“行”“就这个”这种高度依赖上下文的短消息

### 5.3 `selected_skill`

至少要包含：

- `skill_name`
- `skill_description`
- `skill_scope`
- `skill_output`

格式建议：

```text
[SELECTED_SKILL]
skill_name: draft_reply_from_context
skill_description: Draft a reply from existing mailbox context without sending anything.
skill_scope: Read-only drafting workflow. Never send email and never modify mailbox state.
skill_output: A ready-to-send draft reply or one concise clarifying question.
```

作用：

- 告诉 finalizer 这个结果是由什么 skill 产出的
- 告诉它能力边界是什么
- 防止它把 skill 的结果“说大了”

### 5.4 `skill_result`

来源：

- skill executor 的执行结果

建议：

- 优先使用结构化结果
- 如果当前阶段来不及改 executor，也允许先传字符串结果

推荐格式：

```json
{
  "completed": true,
  "skill_result": {
    "subject": "Coffee Chat",
    "body": "Hi Zeng Lin,...",
    "tone": "concise",
    "notes": [
      "draft only",
      "not sent"
    ]
  },
  "reason": "Matched the drafting skill and produced a draft from mailbox context."
}
```

兼容格式：

```json
{
  "completed": true,
  "skill_result": "Here is a concise draft reply...",
  "reason": "Skill completed successfully."
}
```

---

## 6. 核心约束

这一层必须严格遵守下面这些约束。

### 6.1 不允许调用任何工具

- `tools = []`
- 不允许访问邮箱
- 不允许访问日历
- 不允许访问 memory
- 不允许访问 shell

### 6.2 不允许新增事实

它只能使用下面三类信息：

1. `intent`
2. `recent_context`
3. `skill_result`

不允许：

- 补联系人信息
- 猜主题
- 猜邮件内容
- 猜时间
- 猜用户偏好
- 猜 skill 没有明确给出的结论

### 6.3 不允许扩展 skill 边界

如果 skill 是：

- draft only

那 finalizer 不能把回复说成：

- “我已经帮你发出去了”

如果 skill 是：

- summarize only

那 finalizer 不能把回复说成：

- “我已经帮你处理好了这些邮件”

### 6.4 主要工作是整理表达

它可以做的事只有这些：

- 重组句子
- 压缩表达
- 调整语气
- 把 skill 内部结果整理成用户可读回复
- 明确说明结果是否只是草稿、建议或总结

### 6.5 输出必须面向用户

它的最终输出不是内部 trace，也不是执行日志，而是用户真正会看到的回复。

---

## 7. 输出

这一层输出严格 JSON。

固定结构如下：

```json
{
  "final_response": "string",
  "reason": "string"
}
```

### 字段说明

#### `final_response`

- 用户最终会看到的自然语言回复
- 这是这一层最重要的输出
- 必须是完整回复，不能只是片段

#### `reason`

- 简短说明为什么这样组织输出
- 主要用于日志和调试
- 不直接展示给用户

---

## 8. System Prompt 最终版

下面这段可以直接作为 Skill Finalizer 的 system prompt 初稿。

```text
你是 Skill Finalizer。

你的职责只有这些：
1. 读取已经完成的 skill 执行结果
2. 结合 intent 和 recent_context
3. 生成最终给用户看的自然语言回复

你不是执行器，也不是路由器。
你不能调用工具，你不能补充新事实，你不能扩展 skill 的能力边界。

你会收到这些输入：
- intent
- recent_context：最近最多 10 条自然语言对话
- selected_skill：当前 skill 的名称、说明、能力边界、预期输出
- skill_result：skill 已经产出的结果

你必须遵守下面这些规则：
- 你只能依据 intent、recent_context、selected_skill、skill_result 来写 final_response
- 你不能新增任何未在输入中明确支持的事实
- 你不能猜测时间、联系人、邮件主题、邮件内容或执行状态
- 你必须尊重 selected_skill 的 scope，不能把“草稿”说成“已发送”，不能把“总结”说成“已处理”
- 你的工作是整理表达，不是重新完成任务
- 如果 skill_result 本身已经是用户可读内容，你可以轻微整理语气，但不能改写事实
- 输出必须是严格 JSON
- 你不能输出 JSON 以外的任何内容

你的输出 JSON 必须严格使用下面这个结构：
{
  "final_response": "string",
  "reason": "string"
}

字段要求：
- final_response：最终返回给用户的自然语言回复
- reason：简要说明你为什么这样组织回复
```

---

## 9. 后端执行逻辑

这一层的后端逻辑应该尽量简单，不要再引入复杂决策。

### 9.1 推荐控制流

```text
if selected_skill and skill_completed:
    run skill_finalizer_llm
    parse JSON
    if final_response is valid and non-empty:
        return final_response
    else:
        raise error
else:
    fallback to main_agent
```

### 9.2 固定规则

- 只有 skill 已成功完成，才调用 finalizer
- finalizer 只跑一次
- `max_iterations = 1`
- 如果 JSON 解析失败，直接报错，不回退到主 agent
- 如果 `final_response` 为空，直接报错，不回退到主 agent
- 如果 finalizer 报错，直接报错，不回退到主 agent
- 只有 skill 本身未完成时，才允许按原有逻辑回退到主 agent

### 9.3 补充约定

这里额外明确一条实现约束：

- `skill finalizer` 已经属于 skill 成功路径的一部分
- 一旦系统进入这一层，就不再允许因为 finalizer 的 LLM 失败而切回主 agent

原因是：

- 回退到主 agent 会让本轮重新进入更大、更不受限的执行面
- 这会破坏 skill 已经建立的能力边界
- 也会让“skill 成功但 finalizer 失败”的问题被静默掩盖，增加调试成本

---

## 10. 为什么不要把“当前用户原始消息”再传进去

这里明确约定：

- 不把 raw user message 再传给 finalizer

原因是：

1. 上游已经有 `intent`
2. 当前最终回复应该围绕“已经确定的任务”来组织
3. 很多原始消息都非常短，例如“好的”“行”“就这个”
4. 这类消息如果脱离语境，本身信息量很低
5. `recent_context` 已经足够恢复最近语境

所以这一层应该依赖：

- `intent` 来理解当前任务
- `recent_context` 来理解最近语境
- `skill_result` 来理解已经做出来的结果

而不是重新从 raw user message 里推任务。

---

## 11. 示例

### 示例输入

```text
[INTENT]
The user wants a concise draft reply to a recent email.

[RECENT_CONTEXT]
User: 帮我给 zenglin 起草一封邮件
Assistant: 我已经基于最近邮件上下文起草好了草稿。
User: 再简洁一点

[SELECTED_SKILL]
skill_name: draft_reply_from_context
skill_description: Draft a reply from existing mailbox context without sending anything.
skill_scope: Draft only. Never send email and never modify mailbox state.
skill_output: A ready-to-send draft reply.

[SKILL_RESULT]
{
  "completed": true,
  "skill_result": {
    "subject": "Coffee?",
    "body": "Hi Zeng Lin,\n\nWould you like to grab a coffee sometime this week?\n\nBest,\nWenyu"
  },
  "reason": "Draft created successfully."
}
```

### 示例输出

```json
{
  "final_response": "我已经按更简洁的方向整理好了草稿，你可以直接看下面这版：\n\nSubject: Coffee?\n\nHi Zeng Lin,\n\nWould you like to grab a coffee sometime this week?\n\nBest,\nWenyu",
  "reason": "The skill already produced a valid draft, so the response only reframes it as a concise user-facing reply without adding new facts."
}
```

---

## 12. 与当前实现兼容的最小落地方式

如果想先最小改动落地，可以按下面方式接入：

1. 保留现有 skill selector
2. 保留现有 skill executor
3. 当 `skill_execution_result.completed = true` 时，不再直接把 skill 的 `response` 返回给用户
4. 而是把 skill 的 `response` 作为 `skill_result` 传给 finalizer
5. 由 finalizer 输出 `final_response`
6. 如果 finalizer 成功，后端把 `final_response` 返回给用户
7. 如果 finalizer 失败，直接报错，不回退主 agent

这样即使 executor 暂时还是自然语言输出，也可以先把 finalizer 层接上。

后续更理想的版本再继续演进为：

- executor 输出结构化 `skill_result`
- finalizer 专门负责最终用户表达

---

## 13. 一句话总结

Skill Finalizer 只做一件事：

- 在 skill 已经执行成功之后
- 用 `intent + recent_context + skill_result`
- 生成一个不瞎编、不越界的最终 `final_response`

它不选路、不调工具、不补事实，只负责把结果安全地说给用户听。
