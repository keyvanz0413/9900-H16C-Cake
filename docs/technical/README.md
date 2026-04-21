# Technical Documentation

本目录收录 `9900-H16C-Cake`（EmailAI 邮件助手）当前代码库的技术文档。文档按 **模块 / 方案 / 功能** 拆分，每个文件聚焦单一主题，便于定位与维护。

> 仓库根目录下的 `INTENT_LAYER_PLAN.md`、`SERIAL_PLANNER_ARCHITECTURE.md` 等属于 **设计提案**。本目录的文档则以 `email-agent/` 与 `oo-chat/` 中 **实际运行的代码** 为权威来源。

---

## 导航

### 1. Orchestration —— 多 Agent 编排层
`email-agent/intent_layer.py` 与 `email-agent/agent.py` 组成的五阶段流水线。

- [intent-layer.md](orchestration/intent-layer.md) —— Intent 阶段：意图识别、闲聊直答、触发执行
- [planner.md](orchestration/planner.md) —— Planner：串行执行计划与步骤依赖
- [skill-input-resolver.md](orchestration/skill-input-resolver.md) —— 基于 `input_schema` 的参数生成
- [main-agent-step.md](orchestration/main-agent-step.md) —— 通用 Agent 步骤的结构化输出契约
- [finalizer.md](orchestration/finalizer.md) —— Finalizer：唯一对用户发声的阶段
- [orchestrator-flow.md](orchestration/orchestrator-flow.md) —— `IntentLayerOrchestrator` 总入口的执行轨迹
- [memory-store.md](orchestration/memory-store.md) —— Markdown 记忆读写与写手子 Agent

### 2. Skills —— 串行可复用流水线
`email-agent/skills/` 中的 9 个技能 + `registry.yaml` 契约。

- [skill-registry.md](skills/skill-registry.md) —— YAML schema 与字段语义
- [weekly-email-summary.md](skills/weekly-email-summary.md)
- [urgent-email-triage.md](skills/urgent-email-triage.md)
- [bug-issue-triage.md](skills/bug-issue-triage.md)
- [resume-candidate-review.md](skills/resume-candidate-review.md)
- [draft-reply-from-email-context.md](skills/draft-reply-from-email-context.md)
- [send-prepared-email.md](skills/send-prepared-email.md)
- [writing-style-profile.md](skills/writing-style-profile.md)
- [unsubscribe-discovery.md](skills/unsubscribe-discovery.md)
- [unsubscribe-execute.md](skills/unsubscribe-execute.md)

### 3. Providers —— Gmail / Outlook / 日历集成
`email-agent/agent.py` 中的供应商切换与 `plugins/` 中的 ConnectOnion 插件。

- [provider-switching.md](providers/provider-switching.md) —— 基于 `LINKED_GMAIL` / `LINKED_OUTLOOK` 的路由
- [gmail-provider.md](providers/gmail-provider.md) —— `GmailCompat` 与 OpenAI 兼容补丁
- [outlook-provider.md](providers/outlook-provider.md) —— Outlook + Microsoft Calendar
- [calendar-approval-plugin.md](providers/calendar-approval-plugin.md) —— 三路审批（前端 IO / CLI / 无头回退）
- [gmail-sync-plugin.md](providers/gmail-sync-plugin.md) —— 发件后 CRM 同步
- [attachment-text-tool.md](providers/attachment-text-tool.md) —— `extract_recent_attachment_texts`（附件文本抽取）

### 4. Unsubscribe —— 一键退订方案
订阅治理子系统，跨 tool / state / workflow / skill 四层。

- [unsubscribe-overview.md](unsubscribe/unsubscribe-overview.md) —— 总体方案与阶段划分
- [unsubscribe-tool.md](unsubscribe/unsubscribe-tool.md) —— `get_unsubscribe_info` 合并工具
- [unsubscribe-state.md](unsubscribe/unsubscribe-state.md) —— `UNSUBSCRIBE_STATE.json` 数据模型
- [unsubscribe-workflow.md](unsubscribe/unsubscribe-workflow.md) —— 发现 / 执行阶段的公共构件

### 5. Memory —— Markdown 自维护记忆
自然语言文件 + 写手 Agent 的组合方案。

- [markdown-memory.md](memory/markdown-memory.md) —— `USER_PROFILE.md` / `USER_HABITS.md` / `WRITING_STYLE.md`

### 6. Frontend —— `oo-chat` 客户端
Next.js 16 + React 19 + Zustand 的聊天壳。

- [oo-chat-overview.md](frontend/oo-chat-overview.md) —— 应用结构与连接模式
- [chat-api-route.md](frontend/chat-api-route.md) —— `/api/chat` 的 Ed25519 签名与会话传递
- [approval-ui.md](frontend/approval-ui.md) —— 与 `calendar_approval_plugin` 的前端握手

### 7. Deployment —— 部署与环境
Docker Compose 两容器部署。

- [docker-compose.md](deployment/docker-compose.md) —— `email-agent` + `oo-chat` 组合
- [env-vars.md](deployment/env-vars.md) —— 全量环境变量清单与作用域

---

## 与仓库中已有文档的关系

| 位置 | 性质 | 说明 |
|---|---|---|
| 根目录 `*.md`（非 README） | **设计提案 / 规划** | 记录方案演进，可能与当前代码存在细节差异 |
| `docs/agent/`、`docs/workflow/` 等旧目录 | **历史快照 / 上一代架构** | 部分内容指向过时路径，保留以追溯 |
| `docs/technical/`（本目录） | **当前代码的技术说明** | 以实际代码为准，持续更新 |

当设计文档与本目录描述冲突时，以本目录为准；当本目录与代码冲突时，以代码为准。
