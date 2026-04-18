# Email Agent Skill + Guard 改动说明

这份文档记录本次围绕邮件起草与发送确认链路做的结构性修改，重点目标是：

- 让“新建邮件起草”也能走 skill 管线，拿到 writing style 和 sender identity 上下文
- 防止 intent layer 再把 `send` / `reply` / `draft` / `archive` 一类动作错误地短路成纯文本回复
- 让未完成 skill 产出的上下文 bundle 真正传递给 main agent，而不是在 fallback 时丢失

---

## 1. 背景问题

在改动前，系统有三个核心缺口：

1. 现有 skill 本质上是“只读上下文收集器”，不会直接发送邮件
2. `skill_finalizer` 被设计为只能把 skill 结果改写成用户可读文本，不能触发动作
3. skill fallback 到 main agent 时，skill 产出的 `response` 没有透传，导致 writing style / sender identity / 草稿准备信息全部丢失

这意味着单靠“加一个 skill”并不能解决真正的问题：

- 第一轮“给某人发一封新邮件”没有合适的 new-email skill
- 第二轮“发送”这类操作仍可能被 intent layer 直接文本回复短路
- 即便 skill 收集了上下文，只要 `completed=False` 回退到 main agent，这些上下文也会丢失

---

## 2. 本次实现的最终方案

这次实际落地的是四部分组合，不是单独一项：

### 2.1 新增 `compose_new_email_draft` skill

作用：

- 处理 brand-new outbound email 的第一轮起草准备
- 读取 `WRITING_STYLE.md`
- 调用 `get_my_identity`
- 产出一个给 main agent 使用的 bundle
- 明确要求 main agent 后续调用 `send`
- skill 自己绝不发送邮件

输入字段：

- `recipient`
- `topic`
- `key_points`（可选）

这个 skill 的输出不是“最终发出去的邮件”，而是：

- recipient / topic / key points
- writing style
- sender identity
- handoff instructions

然后由 main agent 继续组正文，并走现有 Gmail approval plugin 的 staging + confirmation 流程。

### 2.2 在 `intent_layer` 加硬守

新增 `intent_category` 概念，并在代码里硬编码 direct-response 白名单：

- 允许 direct response 的只有：
  - `meta_chat`
  - `clarification`

其他类别，例如：

- `mailbox_query`
- `mailbox_mutation`
- `calendar_query`
- `calendar_mutation`
- `profile_statement`

即使 LLM 给出很高的 `no_execution_confidence`，也不允许直接把 `final_response` 返回给用户，必须继续往 skill selector / main agent 走。

这一步是本次安全修复的核心，因为它把“是否允许短路”从 prompt 软约束提升成了代码硬约束。

### 2.3 更新 `intent_layer` prompt

`prompts/intent_layer.md` 已同步改成 category-based 决策树，要求模型：

- 必须输出 `intent_category`
- 只有 `meta_chat` / `clarification` 才能返回非空 `final_response`
- 任何 send / reply / draft / forward 请求都不能在 intent layer 直接文本收口

这部分是软保险，用来提高 LLM 正确分类的概率。

### 2.4 修复 skill fallback 时上下文丢失

这是本次实现里非常关键、也最容易被忽略的一点。

原本 `PythonSkillExecutor.run()` 在 skill 返回：

- `completed=False`
- 但 `response` 非空

时，会直接把 `response` 丢弃成 `None`。

这会导致像 `compose_new_email_draft` 这种“准备好上下文，但故意不自己完成发送”的 skill 根本无法把 bundle 传递给 main agent。

本次修复后：

- 只要 skill 返回了非空 `response`
- 就保留这段 `response`
- 即便 `completed=False`，也允许 `_run_main_agent()` 把它放进 `[SKILL_PREPARATION_CONTEXT]`

这样 fallback 才真正有意义。

---

## 3. 具体代码改动

### 3.1 `email-agent/skills/compose_new_email_draft.py`

新增文件。

实现内容：

- 读取 writing style markdown
- 调用 `get_my_identity`
- 输出 `[COMPOSE_NEW_EMAIL_DRAFT_BUNDLE]`
- 在 `[HANDOFF_INSTRUCTIONS]` 里明确要求 main agent：
  - 生成正文
  - 推导 subject
  - 调用 `send`
  - 不要在用户确认前声称“已发送”

### 3.2 `email-agent/skills/registry.yaml`

注册 `compose_new_email_draft` skill，并声明：

- scope
- used tools
- input schema
- 输出语义

### 3.3 `email-agent/intent_layer.py`

主要改动有四块：

1. 增加 `VALID_INTENT_CATEGORIES`
2. 增加 `DIRECT_RESPONSE_CATEGORIES`
3. `IntentDecision` 新增 `intent_category`
4. `_analyze_intent()` 对 `intent_category` 做枚举校验，并对 direct-response 做硬守
5. `PythonSkillExecutor.run()` 保留 `completed=False` 但 `response` 非空的 skill bundle
6. `_run_main_agent()` handoff 增加：
   - `intent_category`
   - `[SKILL_PREPARATION_CONTEXT]`

### 3.4 `email-agent/prompts/intent_layer.md`

把原本以 `no_execution_confidence` 为核心的 direct-response 规则，升级成 category-based 规则：

- `intent_category` 必填
- 只有 `meta_chat` / `clarification` 可直接返回
- mutation / query 请求必须进入后续执行链

### 3.5 `email-agent/tests/test_intent_layer.py`

测试更新包括：

- 原有 intent-agent mock payload 补充 `intent_category`
- 修正 direct-response 边界值，使用 `> 9.0`
- 新增 mailbox mutation 高置信度也不能 direct respond 的测试
- 新增 unknown `intent_category` 必须报错的测试
- 新增 incomplete skill 仍要透传 bundle 到 main agent 的测试
- 新增 `compose_new_email_draft` skill 的执行测试

---

## 4. 实际行为变化

### 场景 1：第一轮新建邮件

用户说：

> 给 Alice 发一封关于下周末户外活动的邮件

现在的预期路径：

1. intent layer 标成 `mailbox_mutation`
2. 不允许 direct response
3. skill selector 命中 `compose_new_email_draft`
4. skill 收集 writing style + sender identity
5. skill 返回 bundle，但 `completed=False`
6. main agent 接收 `[SKILL_PREPARATION_CONTEXT]`
7. main agent 调用 `send`
8. Gmail approval plugin 只 stage draft，不直接发出
9. 用户确认后才真正发送

### 场景 2：第二轮“发送”

用户说：

> 发送

现在 intent layer 即使误生成了某种文本 `final_response`，代码也会因为它属于 `mailbox_mutation` 而丢弃该 `final_response`，继续走后续执行链，不会再出现“文本上说发了，实际上没发”的假完成。

### 场景 3：普通闲聊

用户说：

> 你好

这类 `meta_chat` 请求仍然保留快速 direct-response 通道，不会强行进 skill / main agent。

---

## 5. 为什么这次改动是结构性修复

这次不是在 prompt 上“再提醒模型一次”，而是把关键约束下沉到了代码层：

- LLM 必须输出合法 `intent_category`
- category 不在枚举中直接报错
- 只有白名单 category 才允许 short-circuit
- skill fallback 时 bundle 不再被 executor 吞掉

因此，这个修复不仅覆盖“新建邮件起草”，也会自动保护未来新增的 mutation 类动作，例如：

- archive
- delete
- forward
- calendar create/update
- 其他依赖工具执行和确认链的操作

---

## 6. 验证结果

### 已完成验证

本次已经完成：

- `py_compile` 语法检查通过
- 手工执行了受影响的核心测试函数，覆盖：
  - direct response 白名单
  - mailbox mutation 高置信度不允许直回
  - unknown `intent_category` 报错
  - skill fallback 时 bundle 透传 main agent
  - `compose_new_email_draft` skill 实际执行
  - 相关 orchestrator / selector 路径

### 未完成项

完整 `pytest` 套件本机未直接跑通，原因不是这次改动本身，而是当前本地环境缺依赖：

- 主机环境没有安装 `pytest`
- `uv run --directory email-agent --extra dev ...` 会因为项目里声明的本地 editable 源 `../connectonion` 不存在而失败

因此，这次验证是“核心路径已回归验证”，但不是“完整测试环境全绿”。

---

## 7. 本次新增/修改文件

新增：

- `email-agent/skills/compose_new_email_draft.py`

修改：

- `email-agent/intent_layer.py`
- `email-agent/prompts/intent_layer.md`
- `email-agent/skills/registry.yaml`
- `email-agent/tests/test_intent_layer.py`

---

## 8. 结论

本次改动解决的不是单一 skill 缺失问题，而是整条“新邮件起草 -> stage -> 用户确认 -> 真正发送”链路中的两个结构性缺陷：

1. mutation 请求不能再被 intent layer 误短路
2. skill 准备出的上下文在 fallback 时不会再丢失

在这个基础上，`compose_new_email_draft` 才能真正发挥作用，把第一轮新邮件起草纳入 skill 管线，同时继续复用现有 approval plugin 的确认流。
