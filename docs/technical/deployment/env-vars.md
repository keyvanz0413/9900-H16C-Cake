# 环境变量

本文汇总 `email-agent` 与 `oo-chat` 实际用到的环境变量。范本见 `email-agent/.env.example`（如存在）与 `docker-compose.yml`。

---

## `email-agent`

### LLM 模型

每一阶段可单独指定模型，未指定则 fallback 到 `AGENT_MODEL`。

| 变量 | 默认 | 作用阶段 |
|---|---|---|
| `AGENT_MODEL` | `co/claude-sonnet-4-5` | Main agent 步骤 |
| `INTENT_LAYER_MODEL` | `AGENT_MODEL` | Intent agent |
| `PLANNER_MODEL` | `INTENT_LAYER_MODEL` | Planner |
| `SKILL_INPUT_RESOLVER_MODEL` | `PLANNER_MODEL` | Skill Input Resolver |
| `FINALIZER_MODEL` / `SKILL_FINALIZER_MODEL` | `INTENT_LAYER_MODEL` | Finalizer |
| `WRITING_STYLE_MODEL` | `INTENT_LAYER_MODEL` | WRITING_STYLE writer |
| `USER_MEMORY_MODEL` | `INTENT_LAYER_MODEL` | User memory writer |

推荐策略：Intent / Planner / Resolver / Finalizer 用便宜快速模型，Main agent 用更强模型。

### Provider 切换

| 变量 | 含义 |
|---|---|
| `LINKED_GMAIL` | `"true"` 显式启用 Gmail |
| `LINKED_OUTLOOK` | `"true"` 显式启用 Outlook |
| `GOOGLE_ACCESS_TOKEN` / `GOOGLE_REFRESH_TOKEN` | Gmail OAuth（没显式 flag 时自动识别） |
| `MICROSOFT_ACCESS_TOKEN` / `MICROSOFT_REFRESH_TOKEN` | Outlook OAuth（同上） |

Gmail 与 Outlook 同时满足时 **优先 Gmail**。测试环境（`PYTEST_CURRENT_TEST` / `CI`）默认都不启用，避免误连。

### 记忆 / 状态路径

| 变量 | 默认 | 作用 |
|---|---|---|
| `UNSUBSCRIBE_STATE_PATH` | `email-agent/UNSUBSCRIBE_STATE.json` | 退订状态 JSON |
| `HOME` | 容器内 `/app` | ConnectOnion 默认把 `.co/` 放在 `$HOME/.co/` |

Markdown 记忆的路径在 `agent.py` 硬编码到 `BASE_DIR`，Docker 部署通过 volume 把它们映射到宿主机。

### 运行时

| 变量 | 默认 | 作用 |
|---|---|---|
| `AGENT_TIMEZONE` / `TZ` | `Australia/Sydney` | 注入到 Agent prompt，保持时间解释稳定 |
| `EMAIL_AGENT_TRUST` | `open`（compose 默认） | 签名验证策略 |

---

## `oo-chat`

### 构建期（`NEXT_PUBLIC_*`）

| 变量 | 作用 |
|---|---|
| `NEXT_PUBLIC_USE_DEFAULT_AGENT` | `"true"` 启用 default agent 主页，不展示地址簿 |
| `NEXT_PUBLIC_DEFAULT_AGENT_NAME` | 默认显示名 |
| `NEXT_PUBLIC_DEFAULT_AGENT_URL` | 供浏览器端读取（与 server 端 `DEFAULT_AGENT_URL` 一起使用） |

`NEXT_PUBLIC_*` 在 `docker compose build` 时被冻结；改动后必须 `--build`。

### 运行时

| 变量 | 作用 |
|---|---|
| `DEFAULT_AGENT_URL` | Server route 转发目标（容器内 DNS：`http://email-agent:8000`） |
| `OO_CHAT_PORT` | 宿主机暴露端口，默认 3300（映射到容器 3000） |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `GEMINI_API_KEY` | LLM 直连模式（非默认路径） |

---

## Secrets

- **不要把 `.env` 提交到仓库**：`.gitignore` 已默认排除。
- **OAuth token** 本质上是短期凭证；Google/Microsoft 允许吊销，万一泄露可在控制台重置。
- **ConnectOnion 私钥**：位于 `email-agent/.co/`，这是 agent 的身份；丢失会导致之前签发的认证关系失效。建议和其他 secrets 一起备份。
- **LLM API key**：各供应商独立，建议每个部署环境分独立 key，便于审计/限额。

---

## 快速自检

```bash
# Gmail 路径是否生效？
docker compose exec email-agent env | grep -E 'LINKED_|GOOGLE_'

# 各阶段模型分配
docker compose exec email-agent env | grep -E 'AGENT_MODEL|_MODEL$'

# oo-chat 指向哪个 agent？
docker compose exec oo-chat printenv DEFAULT_AGENT_URL
```
