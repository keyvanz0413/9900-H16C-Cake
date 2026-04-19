# Serial Planner 架构执行规范

这份文档定义新的串行执行架构。

这版架构的核心目标是：

- 保留现有 `Intent Layer`
- 把当前 `skills selector` 改造成 `planner`
- 支持多个 `skill` 串行执行
- 支持 `skill + 主 agent` 混合执行
- 把“选 skill”与“填 skill 参数”拆开
- 所有 step 执行完后，只在最后统一跑一次 `finalizer`

这份文档是当前方案的实现依据，后续开发默认按这里执行。

---

## 1. 总体原则

### 1.1 Intent Layer 不变

本次重构不改 `Intent Layer` 的职责。

`Intent Layer` 继续负责：

- 理解当前用户目的
- 结合上下文判断当前请求
- 产出 `intent`
- 保持现有的上下文理解方式

本次新方案从 `Intent Layer` 之后开始接入。

### 1.2 selector 改成 planner

当前的 `skills selector` 只能处理：

- 是否走 skill
- 走哪个单一 skill
- 顺手填这个 skill 的参数

这会限制系统只能走单 skill 快速路径。

新的设计是：

- 不再只选一个 skill
- 而是生成一串按顺序执行的 `steps`

### 1.3 skill 参数不再由 planner 填

新的规划层只负责：

- 规划要执行哪些 step
- step 的顺序
- 哪一步是 `skill`
- 哪一步是 `agent`
- 每一步依赖前面哪几步的结果

它不再负责：

- 直接输出 `skill_arguments`

`skill_arguments` 改由每个 skill 前面的一个小 LLM 单独生成。

### 1.4 finalizer 只在最后执行一次

不是每个 skill 后面都挂一个 finalizer。

正确位置是：

- 所有 step 全部执行完后
- 再统一跑一次最终 `finalizer`

它读取：

- `intent`
- `older_context`
- `recent_context`
- 所有 step 的结果

然后输出最终：

```json
{
  "final_response": "string"
}
```

---

## 2. 新的整体流程

```text
用户消息
-> Intent Layer
-> Planner
-> 串行执行 steps
   -> 如果是 skill step：先过 skill-input-resolver，再执行 skill
   -> 如果是 agent step：执行主 agent
-> Finalizer
-> final_response
```

---

## 3. 角色分工

### 3.1 Intent Layer

职责：

- 产出整体 `intent`
- 保留现有上下文理解能力

不负责：

- 选 skills
- 排执行步骤
- 填 skill 参数

### 3.2 Planner

职责：

- 根据 `intent` 和上下文决定本轮执行计划
- 产出串行的 `steps`
- 确定每一步的顺序
- 确定哪一步需要读取哪些前序 step 结果
- 决定是否需要主 agent

不负责：

- 执行 tools
- 填 `skill_arguments`
- 输出最终用户回复

### 3.3 Skill Input Resolver

职责：

- 只为当前 skill 填 `skill_arguments`

不负责：

- 决定要不要用这个 skill
- 决定顺序
- fallback
- 输出最终用户回复

### 3.4 Skill Executor

职责：

- 执行当前 skill
- 使用已经生成好的 `skill_arguments`
- 产出该 step 的结果

### 3.5 Main Agent Step

职责：

- 处理 planner 明确交给主 agent 的那一步
- 读取 planner 指定的前序结果
- 处理 skills 之外的开放式任务

### 3.6 Finalizer

职责：

- 在所有 step 执行完后统一读取结果
- 生成最终用户回复

不负责：

- 调 tool
- 改执行计划
- 重跑 skill

---

## 4. Planner 输入

Planner 的上下文输入方式先保持和当前系统一致，不在本轮重构中改动它的上下文窗口策略。

也就是说：

- 上下文输入先沿用当前实现
- 当前系统如果已有短上下文 / 长上下文拆分，就继续沿用
- 当前系统如果只给某一部分上下文，也先继续沿用

本轮的重点不在改 planner 的上下文输入边界，而在改 planner 的输出职责。

Planner 至少应获得：

1. `intent`
2. 当前会话上下文
3. 当前可用的所有 skills 说明
4. 每个 skill 的能力边界
5. 每个 skill 的 `input_schema`

---

## 5. Planner 输出

Planner 输出严格 JSON。

建议结构如下：

```json
{
  "steps": [
    {
      "step_id": "step_1",
      "type": "skill",
      "name": "weekly_email_summary",
      "goal": "Summarize recent inbox activity.",
      "reads": []
    },
    {
      "step_id": "step_2",
      "type": "agent",
      "goal": "Handle any remaining open-ended work after reading the summary.",
      "reads": ["step_1"]
    }
  ],
  "reason": "string"
}
```

### 5.1 字段说明

#### `steps`

- 一个有序数组
- 数组顺序就是执行顺序
- 所有 step 一律串行执行

#### `step_id`

- 每一步的唯一 id
- 供后续 `reads` 引用

#### `type`

只允许两种：

- `skill`
- `agent`

#### `name`

- 只有 `skill` step 需要
- 必须对应某个已注册的 skill 名称

#### `goal`

- 当前这一步要完成什么
- 用自然语言描述当前 step 的目标

#### `reads`

- 当前 step 需要读取哪些前序 step 的结果
- 使用 `step_id` 数组表示
- 如果当前 step 不依赖前序结果，就返回空数组 `[]`

#### `reason`

- 说明为什么这样安排这串 steps

### 5.2 关于是否需要主 agent

不再额外输出一个布尔值来表示“要不要主 agent”。

规则直接写死为：

- 如果 `steps` 中包含 `type = "agent"`，说明这轮需要主 agent
- 如果 `steps` 中不包含 `agent` step，说明 planner 判断这轮所有任务都可以通过 skills 完成

### 5.3 关键原则

只有一种情况不调用主 agent：

- planner 判断当前任务的全部部分都能由规划出的 skill steps 完成

否则：

- planner 必须在某个位置加入 `agent` step

---

## 6. Skill Input Resolver

每个 `skill step` 在真正执行之前，都要先经过一个小 LLM。

这个小 LLM 不是 planner，也不是 finalizer。

它唯一职责是：

- 给当前这个 skill 生成 `skill_arguments`

### 6.1 输入

它只接收下面这些输入：

1. `intent`
2. 当前 step 的 `goal`
3. 当前 skill 的：
   - `name`
   - `description`
   - `scope`
   - `input_schema`
4. `reads` 指定的前序 step 结果

### 6.2 不输入的内容

这层不输入：

- 当前对话上下文
- `older_context`
- `recent_context`
- 当前用户原始消息
- 整体执行计划全文
- 所有其他 skills 的信息

原因是：

- 这一层不是做全局理解
- 它只负责把当前 step 所需参数填出来
- 输入越小越不容易发散

### 6.3 输出

它只输出严格 JSON：

```json
{
  "skill_arguments": {}
}
```

这层不输出：

- `can_execute`
- `reason`
- fallback 决策

### 6.4 职责边界

Skill Input Resolver 不负责：

- 判断这一步应不应该存在
- 判断要不要换 skill
- 判断要不要主 agent
- 判断是否回退

这些事情都已经在 planner 那一层决定好了。

---

## 7. Skill Step 执行规则

当某个 step 的 `type = "skill"` 时，运行顺序固定如下：

```text
读取当前 step
-> 读取 reads 指定的前序 step 结果
-> 调用 Skill Input Resolver
-> 获得 skill_arguments
-> 按 input_schema 做后端校验
-> 执行 skill
-> 保存 step_result
```

### 7.1 skill 输入来源

skill 的实际输入由三部分组成：

1. planner 指定的当前 step
2. Skill Input Resolver 产出的 `skill_arguments`
3. `reads` 指定的前序 step 结果

### 7.2 skill 不直接决定全局流程

skill 只执行自己这一步。

它不负责：

- 改 planner
- 插入新 step
- 改主 agent 顺序

---

## 8. Agent Step 执行规则

当某个 step 的 `type = "agent"` 时：

- runtime 按 planner 给出的顺序执行
- runtime 读取 `reads` 指定的前序 step 结果
- 再把这些前序结果与当前 step 的 `goal` 一起交给主 agent

这意味着主 agent 也是一个普通 step，只是类型不同。

---

## 9. Step Result 结构

每一步执行完后，都应该保存一个结构化的 `step_result`。

建议结构如下：

```json
{
  "step_id": "step_1",
  "type": "skill",
  "name": "weekly_email_summary",
  "status": "completed",
  "artifact": {},
  "reason": "string"
}
```

### 9.1 字段说明

#### `step_id`

- 对应 planner 输出里的 step id

#### `type`

- `skill` 或 `agent`

#### `name`

- 对 skill step 填 skill 名称
- agent step 可省略或写 `main_agent`

#### `status`

当前建议先至少支持：

- `completed`
- `failed`

如果后面需要，也可以加入：

- `partial`

#### `artifact`

- 当前 step 的核心结果
- 推荐尽量结构化

#### `reason`

- 当前 step 的执行说明
- 主要用于日志和调试

### 9.2 reads 的含义

如果某个 step 的：

```json
"reads": ["step_1", "step_2"]
```

那就表示：

- runtime 在执行这个 step 前
- 只把 `step_1` 和 `step_2` 的结果传给它

不是让模型自己从所有历史结果里挑，而是由 runtime 先裁好再给。

---

## 10. Finalizer

Finalizer 只在整个执行链最后运行一次。

不是：

- 每个 skill 后都跑一个 finalizer

而是：

- 所有 steps 全部跑完
- 再统一汇总

### 10.1 输入

Finalizer 需要读取：

1. `intent`
2. `older_context`
3. `recent_context`
4. 所有 step 的结果

这里明确约定：

- `older_context + recent_context` 都要给
- 不要只给 `recent_context`

### 10.2 输出

Finalizer 输出严格 JSON：

```json
{
  "final_response": "string"
}
```

### 10.3 职责

Finalizer 只负责：

- 结合整体目的
- 结合上下文
- 结合所有 step 的结果
- 生成最终用户回复

它不负责：

- 重新规划
- 调 tool
- 改 step 顺序
- 重跑 skill

---

## 11. 新架构的一句话总结

新的执行链是：

- `Intent Layer` 继续理解整体目的
- `Planner` 负责产出串行 steps
- 每个 `skill step` 执行前先由一个小 LLM 单独生成 `skill_arguments`
- `agent step` 按 planner 位置串行执行
- 最后只跑一次 `Finalizer`
- `Finalizer` 读取 `intent + older_context + recent_context + 全部 step 结果`
- 最终输出：

```json
{
  "final_response": "string"
}
```
