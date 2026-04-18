# Intent Layer 最终实现规范

这份文档用于指导后续实现，默认按照这里的定义直接开发，不再按“草案”理解。

目标不是立刻替换现有主 agent，而是先在主 agent 前面增加一层轻量 LLM 调用，用来：

- 读取对话上下文
- 判断用户当前目的
- 判断当前请求能不能直接返回
- 判断是否需要进入后续执行层
- 给出置信度
- 输出“用户当前要干什么”的摘要，供下一层继续判断
- 持续总结用户信息 / 用户习惯并落盘，供后续层读取

---

## 1. 总体目标

当前系统的问题是：

- 主 agent 每轮都要读很多上下文
- 主 agent 每轮都要带很大的 prompt 和工具列表
- 很多简单请求其实不需要进入完整执行链
- 一些短回复如“好”“就这个”很容易歧义

本方案的目标是：

1. 在主 agent 前面增加一个 `Intent Layer`
2. 由这一层优先理解上下文和当前目的
3. 能直接返回的请求就直接返回
4. 不能直接返回时，先把“用户当前要干什么”的摘要交给下一层
5. 下一层再判断要不要进入 `skills` 或主 agent 执行流程
6. 把用户长期信息和使用习惯沉淀到单独的 Markdown 文件中

---

## 2. 新的执行流程

```text
用户消息
-> Intent Layer
   - 读取全量上下文
   - 重点关注最近对话
   - 判断当前目的
   - 判断是否能直接返回
   - 输出置信度
   - 输出用户当前目的摘要
   - 更新用户摘要 / 用户习惯
-> 如果可直接返回且置信度 > 8
   -> 直接返回给用户
-> 否则
   -> 进入第二层判断是否走 skills
-> 如果第二层不走 skills 或 skills 无法完成
   -> 回退到现有主 agent + 工具流程
-> 执行完成后
   -> 更新摘要文件 / 用户习惯文件
```

---

## 3. Intent Layer 的定位

Intent Layer 不是：

- 规则路由器
- 正则匹配器
- 最终执行器

Intent Layer 是：

- 一个单独的 LLM 调用
- 一个轻量语义判断层
- 一个上下文压缩和状态抽取层
- 一个直接返回 / 后续执行 的前置判断层

它的职责是“先理解”，不是“替主 agent 完成所有事情”。

---

## 4. Intent Layer 输入

这一层输入所有上下文对话，但 system prompt 要明确告诉它：

- 需要参考完整上下文
- 但要优先看最近的上下文对话
- 最近几轮对话对当前意图判断权重更高
- 不要被很早以前的旧话题误导

### 上下文窗口策略

为了避免输入过长，Intent Layer 不直接读取无限长历史。

最终约定：

- 总输入窗口上限：`50` 条对话项
- 分成两段，显式传入，不重复
- 第一段：`更早的对话（older_context）`，最多 `40` 条
- 第二段：`最近的对话（recent_context）`，最多 `10` 条

### 对话项定义

这里的“对话项”按自然语言消息统计，不按 turn 统计。

- 包含：用户消息、agent 的自然语言回复
- 不包含：工具调用记录、工具结果原始 trace、系统 prompt
- 如果后端内部有工具结果，需要先压成自然语言摘要后再决定是否进入上下文

### 传入方式

建议在调用时显式分段，不要混成一整块文本。

例如：

```text
[OLDER_CONTEXT]
这里是更早的 40 条对话
这些不是最新上下文
可以参考，但优先级低于最近对话

[RECENT_CONTEXT]
这里是最近的 10 条对话
这是当前意图判断的主要依据
```

### 约束

- `older_context` 和 `recent_context` 不能重复
- 两段都要显式标注
- 模型必须优先参考 `recent_context`
- 模型可以在需要时参考 `older_context`
- 如果两段信息冲突，优先相信最近对话

### 输入建议

1. 当前用户消息
2. `older_context`（更早 40 条对话，显式标注）
3. `recent_context`（最近 10 条对话，显式标注）
4. 当前会话状态（如果后面引入）
5. 用户长期摘要文件
6. 用户习惯摘要文件

### 对模型的 system prompt 约束

这一层的 system prompt 需要明确要求它：

- 你的工作是判断当前用户意图和是否需要后续执行
- 你必须优先参考最近上下文
- 你可以参考更早的历史，但最近上下文优先级更高
- 你必须输出结构化结果
- 你必须对关键判断输出置信度
- 你不能在不确定时武断直返
- 输入中会显式给你 `older_context` 和 `recent_context`
- 你必须主要参考 `recent_context`
- 只有在必要时才参考 `older_context`
- 如果两段信息冲突，默认以 `recent_context` 为准

---

## 5. Intent Layer 输出

这一层建议统一输出结构化 JSON，而不是自然语言段落。

### 建议输出字段

```json
{
  "intent": "string",
  "no_execution_confidence": 0,
  "final_response": null,
  "reason": "string",
  "user_update_summary": "string"
}
```

### 字段说明

#### `intent`
- 用一句话总结“用户当前要干什么”
- 如果要进入后续层，后续层主要就看这一句

#### `no_execution_confidence`
- 对“本轮不需要进入后续执行层”的置信度
- 取值范围建议：`0-10`
- 这是第一层最关键的判断值
- 如果 `no_execution_confidence > 8`，则允许直接返回
- 如果 `no_execution_confidence <= 8`，则必须进入后续层

#### `final_response`
- 如果 `no_execution_confidence > 8`，这里必须返回给用户的最终回复
- 如果 `no_execution_confidence <= 8`，这里写 `null`

#### `reason`
- 简要解释为什么这么判断

#### `user_update_summary`
- 本轮识别出的用户信息 / 用户习惯更新摘要
- 不需要结构化数组
- 只要输出一句或一段自然语言说明即可
- 后面会再交给另一个 LLM 专门处理

---

## 5.1 Intent Layer System Prompt 草案

下面这段按最终实现要求写入第一层 system prompt。

```text
你是 Intent Layer。

你的职责只有这些：
1. 判断用户当前目的是什么
2. 判断本轮是否不需要进入后续执行层
3. 如果不需要后续执行且置信度足够高，直接给用户最终回复
4. 如果需要后续执行，用一句话总结“用户当前要干什么”
5. 提取本轮新增的用户信息和用户习惯更新摘要

你会收到这些输入：
- 当前用户消息
- older_context：更早的对话，最多 40 条
- recent_context：最近的对话，最多 10 条
- 用户长期摘要
- 用户习惯摘要

你必须遵守下面这些规则：
- 主要参考 recent_context
- 只有在必要时才参考 older_context
- 如果 older_context 和 recent_context 冲突，以 recent_context 为准
- 你不能使用正则或关键词硬匹配思维
- 你必须做语义判断
- 你必须输出严格 JSON
- 你不能输出 JSON 以外的任何内容
- 所有置信度都使用 0 到 10 的数字
- 只有 no_execution_confidence > 8 时，后端才会直接返回
- 如果 no_execution_confidence > 8，你必须同时给出 final_response
- 如果 no_execution_confidence <= 8，final_response 必须是 null
- intent 必须用一句话总结用户当前要干什么
- user_update_summary 只需要自然语言一句或一段话，不需要结构化

你的输出 JSON 必须严格使用下面这个结构：
{
  "intent": "string",
  "no_execution_confidence": 0,
  "final_response": null,
  "reason": "string",
  "user_update_summary": "string"
}

字段要求：
- intent：用一句话总结用户当前要干什么
- no_execution_confidence：你对“不需要进入后续执行层”的置信度，0-10
- final_response：如果 no_execution_confidence > 8，这里写最终回复，否则写 null
- reason：简要说明你的判断原因
- user_update_summary：本轮新增的用户信息和用户习惯更新摘要，自然语言即可
```

---

## 6. 直接返回判断规则

这里不是用正则，也不是用硬规则，而是由：

- 第一层 LLM 输出 `no_execution_confidence`
- 后端按固定阈值做分流

也就是说：

- LLM 负责打分
- 后端负责决定是否继续执行

这个判断不是由 LLM 自己决定后续是否跳转，而是由后端逻辑写死。

### 后端固定决策逻辑

#### 情况 A：可以直接返回

当满足：

- `no_execution_confidence > 8`

则：

- 直接返回 `final_response`
- 不进入后续 skills 或主 agent

#### 情况 B：不允许直接返回

- `no_execution_confidence <= 8`

则后端必须：

- 不直接返回
- 进入第二层 skills 判断

### 固定原则

- 只有“能直接返回”这件事非常确定时，才允许直返
- 置信度不够高，就必须走后续执行层

### 职责边界

第一层不负责推荐 `skills`。

第一层只负责：

1. 判断能不能直接返回
2. 如果不能直接返回，总结“用户当前要干什么”

也就是说，第一层的核心产物是：

- 当前目的一句话摘要
- “不需要后续执行”的置信度
- 可直返时的最终回复
- 判断原因
- 用户更新摘要

---

## 7. 第二层：Skills 判断层

Intent Layer 之后，不是立刻进入 `skills`，而是先进入第二层判断。

第二层负责做下面这件事：

- 根据第一层输出的“当前目的摘要”
- 判断这次要不要走 `skills`
- 如果要走，选择哪个 `skill`
- 如果不适合走 `skills`，就回退到现有主 agent

### 第二层定位

- 作为快速路径判断层
- 负责 skill 选择
- 负责决定是否直接进入主 agent
- 不负责长期上下文总结

### 第二层输入

第二层固定输入：

1. `intent`
2. 当前用户消息
3. 最近少量原始对话
4. 当前会话状态
5. skills 清单

### Skills 总表位置

后续所有 skills 的唯一机器可读来源固定为：

- [registry.yaml](/Users/dingwenyu/Desktop/9900-H16C-Cake/email-agent/skills/registry.yaml)

这份 YAML 文件是后端运行时的技能注册表，职责是：

- 记录当前有哪些 skills
- 记录每个 skill 的用途
- 记录每个 skill 的能力边界
- 记录每个 skill 可使用的工具范围

后续第二层只需要读取这一份 YAML 文件，不再依赖根目录 Markdown 文档来获取 skills 信息。

### 为什么放在这里

固定放在 `email-agent/skills/registry.yaml`，原因是：

- 这是后端运行时配置，不是纯说明文档
- 以后可以和每个 skill 自己的 prompt / 说明文件放在同一个目录
- 避免把根目录变成运行时配置仓库
- 让第一层、第二层、主 agent 都有统一读取入口

### registry.yaml 结构要求

这份 YAML 文件建议固定为如下结构：

```yaml
skills:
  - name: compose_email_from_context
    description: 基于历史邮件和 memory 起草邮件草稿
    scope: 只能起草邮件，不能真正发送
    allowed_tools:
      - search_emails
      - read_memory
      - get_email_body
      - get_sent_emails
    output: email_draft
```

### 字段说明

#### `name`
- skill 的唯一标识
- 第二层输出 `skill_name` 时必须引用这里的 `name`

#### `description`
- 给第二层看的简要功能说明
- 用于判断这个 skill 能不能覆盖当前 intent

#### `scope`
- 明确写这个 skill 的能力边界
- 要把“能做什么”和“不能做什么”说清楚

#### `allowed_tools`
- 这个 skill 允许使用的工具列表
- 后面真正实现 skill 时，应以这里为准做工具裁剪

#### `output`
- 这个 skill 的预期产物类型
- 例如：`email_draft`、`email_summary`、`meeting_proposal`

### skills 清单输入格式

第二层必须显式收到当前有哪些 skills，以及每个 skill 的能力边界。

建议按下面这种格式传给第二层：

```text
[AVAILABLE_SKILLS]
- skill_name: compose_email_from_context
  description: 基于历史邮件和 memory 起草邮件草稿
  scope: 只能起草邮件，不能真正发送

- skill_name: summarize_recent_emails
  description: 总结最近邮件
  scope: 只能读和总结邮件，不能修改邮件

- skill_name: propose_meeting_slots
  description: 基于日历和上下文提出会议时间建议
  scope: 只能提出建议，不能直接创建会议
```

第二层 system prompt 必须明确告诉 LLM：

- 当前有哪些 skills
- 每个 skill 只能完成特定功能
- 不能把 skill 的能力范围扩大理解
- 如果没有任何 skill 能覆盖当前 intent，就不要硬选 skill
- 第二层读取的 skill 名称必须来自 `registry.yaml`

### 第二层输出 JSON

第二层必须输出严格 JSON，结构固定如下：

```json
{
  "should_use_skill": false,
  "skill_name": null,
  "reason": "string"
}
```

### 字段说明

#### `should_use_skill`
- 布尔值
- `true` 表示本轮应该直接走 skill 快速路径
- `false` 表示不应走 skill，应直接进入现有主 agent

#### `skill_name`
- 当 `should_use_skill = true` 时，必须是某个现有的 skill 名称
- 当 `should_use_skill = false` 时，必须为 `null`

#### `reason`
- 简要说明为什么选这个 skill，或者为什么不该走 skill

### 第二层 System Prompt 规范

下面这段按最终实现要求写入第二层 system prompt：

```text
你是 Skills Selector。

你的职责只有这些：
1. 读取第一层输出的 intent
2. 查看当前有哪些可用 skills
3. 理解每个 skill 只能完成什么特定功能
4. 判断当前请求是否适合直接走某个 skill
5. 如果适合，选出唯一一个最匹配的 skill
6. 如果不适合，就明确返回不走 skill

你会收到这些输入：
- intent：第一层输出的用户当前目的摘要
- 当前用户消息
- recent_context：最近少量原始对话
- 当前会话状态
- available_skills：当前可用 skills 列表及其能力边界

你必须遵守下面这些规则：
- 你必须基于语义判断，不能用正则或关键词硬匹配
- 你必须严格尊重每个 skill 的能力范围
- skill 只能完成它被定义允许完成的功能
- 如果当前 intent 超出 skill 能力边界，就不要选 skill
- 如果没有明显合适的 skill，就返回 should_use_skill = false
- 你必须输出严格 JSON
- 你不能输出 JSON 以外的任何内容

你的输出 JSON 必须严格使用下面这个结构：
{
  "should_use_skill": false,
  "skill_name": null,
  "reason": "string"
}

字段要求：
- should_use_skill：是否应该直接走 skill
- skill_name：如果 should_use_skill = true，则必须是 available_skills 中的某个 skill_name；否则必须是 null
- reason：简要说明判断原因
```

### 第二层执行流程

```text
Intent Layer
-> 输出 intent
-> 第二层判断 should_use_skill
-> 如果 should_use_skill = true
   -> 执行 selected_skill
   -> 如果 skill 完成
      -> 返回
   -> 如果 skill 无法完成
      -> 回退到现有主 agent + 全量工具
-> 如果 should_use_skill = false
   -> 直接进入现有主 agent + 全量工具
```

### 对 skills 的约束

- skills 先只当快速路径
- skills 不作为能力边界
- skills 没命中时，不能阻止系统继续走工具层
- 第一层不做 skill 判断，第二层单独判断

---

## 8. 用户信息 / 用户习惯落盘

这一层除了做意图判断，还要负责长期沉淀用户信息。

目标是让系统“越用越聪明”。

### 需要沉淀的两类信息

#### 1. 用户信息
例如：

- 用户名字
- 常用邮箱地址
- 用户所在组织 / 团队
- 常联系的人
- 用户常见项目 / 业务背景

#### 2. 用户习惯
例如：

- 偏好的邮件语气
- 偏好的签名风格
- 常用语言
- 常见工作时间 / 开会偏好
- 常见行为模式

---

## 9. 落盘文件建议

当前先设计成两个 Markdown 文件：

- `USER_PROFILE.md`
- `USER_HABITS.md`

建议放在项目根目录，后面也可以迁移到 `email-agent/data/`。

### `USER_PROFILE.md`

适合记录相对稳定的信息：

- 用户基本身份信息
- 组织背景
- 常联系人
- 长期项目背景

### `USER_HABITS.md`

适合记录动态习惯：

- 邮件偏好
- 回复风格
- 时间偏好
- 工作节奏

---

## 10. Intent Layer 与落盘的关系

每轮经过 Intent Layer 后：

1. 读取现有 `USER_PROFILE.md`
2. 读取现有 `USER_HABITS.md`
3. 结合当前上下文判断是否有新增信息
4. 生成结构化更新
5. 由后续写入层把这些更新落盘

### 注意

Intent Layer 先不直接自己写文件。

更稳的做法是：

- Intent Layer 负责提出更新建议
- 由后续单独写入步骤负责写 Markdown

这样以后接上下文压缩插件、提取插件、审核插件会更清晰。

---

## 11. 为什么这一层有意义

如果这层成立，就可以减少后续大模型调用的负担。

### 可以减少的内容

- 主 agent 重新理解上下文的成本
- `re_act` 那类额外“理解意图”的调用负担
- 简单问题进入完整执行链的浪费
- 为第二层提供稳定的目的摘要

### 不能直接减少但可以为后续优化打基础的内容

- 全量工具 schema 的 token
- 超长历史消息的 token

这部分后面可以通过：

- 上下文压缩插件
- 历史摘要插件
- 技能固化
- 工具裁剪

继续优化。

---

## 12. 实现顺序

### 第一阶段

先新增 Intent Layer 的设计和输出格式，不替换主 agent。

### 第二阶段

接入直返逻辑：

- 简单请求直接返回
- 置信度不够则继续走后续流程

### 第三阶段

加入第二层 skills 判断：

- 第一层只输出当前目的摘要
- 第二层再判断是否命中 skills

### 第四阶段

接入用户信息 / 用户习惯落盘。

### 第五阶段

再考虑：

- 上下文压缩
- 历史提取插件
- 是否逐步替代 `re_act`

---

## 13. 最终版本一句话总结

先增加一个轻量的 Intent Layer：

- 读全部上下文，但重点看最近对话
- 判断当前目的
- 输出“不需要后续执行”的置信度
- 只有置信度大于 8 时才直接返回最终回复
- 如果不能直接返回，就输出“用户当前要干什么”的一句话摘要
- 再由第二层判断要不要走 skill
- skill 不行再交给现有主 agent
- 同时持续总结用户信息和用户习惯并落盘

这层的重点不是限制能力，而是：

- 减少无意义的大调用
- 给后续层更清晰的任务摘要
- 为未来的上下文压缩和长期个性化打基础
