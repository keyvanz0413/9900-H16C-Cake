# Docker Compose 部署

## 服务组成

`docker-compose.yml` 定义两个服务：

```
email-agent   :8000  (内部)
oo-chat       :3000  → 宿主机 ${OO_CHAT_PORT:-3300}
```

- `email-agent`：Python agent runtime（`email-agent/Dockerfile`）。
- `oo-chat`：Next.js 前端（`oo-chat/Dockerfile`）。
- 网络：Compose 默认 bridge 网络，`oo-chat` 通过 DNS 名 `email-agent:8000` 访问 agent。

---

## `email-agent` 服务

```yaml
build: ./email-agent
container_name: email-agent
env_file:
  - path: ./email-agent/.env   # required: false
environment:
  HOME: /app
  EMAIL_AGENT_TRUST: open
volumes:
  - ./email-agent/.env:/app/.env
  - ./email-agent/.co:/app/.co
  - ./email-agent/data:/app/data
  - ./email-agent/USER_PROFILE.md:/app/USER_PROFILE.md
  - ./email-agent/USER_HABITS.md:/app/USER_HABITS.md
  - ./email-agent/WRITING_STYLE.md:/app/WRITING_STYLE.md
```

要点：

- **`.env` 不强制存在**：第一次跑可先不给，进入容器执行 `setup` 再填。
- **`.co/` 挂载**：ConnectOnion 身份（Ed25519 密钥）落在这里，必须持久化，否则重启换身份。
- **`data/`**：memory、CRM 数据库等运行时状态。
- **三份 Markdown 记忆文件** 直接从宿主机挂进去，宿主机可以用 git 管理或手工编辑。
- **`EMAIL_AGENT_TRUST=open`**：agent 服务端开放签名验证策略（前端无需事先注册）；生产部署可改成更严格的模式。

---

## `oo-chat` 服务

```yaml
build:
  context: ./oo-chat
  args:
    NEXT_PUBLIC_USE_DEFAULT_AGENT: "true"
    NEXT_PUBLIC_DEFAULT_AGENT_NAME: "Email Agent"
depends_on: [email-agent]
environment:
  DEFAULT_AGENT_URL: http://email-agent:8000
ports:
  - "${OO_CHAT_PORT:-3300}:3000"
```

要点：

- `NEXT_PUBLIC_*` 是 **build arg**，Next.js 在构建期冻结这些值并内嵌到产物；`docker compose build` 时决定。
- 运行期用 `DEFAULT_AGENT_URL` 指向 compose 内部 DNS。
- 宿主机访问：`http://localhost:3300`（默认）或自定义 `OO_CHAT_PORT`。

---

## 常用命令

```bash
# 初始化 agent（OAuth 等）
docker compose run --rm email-agent setup

# 前台运行（看日志方便）
docker compose up --build

# 后台
docker compose up --build -d

# 停止并清理
docker compose down
```

---

## 持久化 checklist

以下文件/目录 **必须持久化**，否则重启丢数据：

| 路径 | 内容 |
|---|---|
| `email-agent/.co/` | ConnectOnion 密钥、会话 checkpoint |
| `email-agent/data/` | 运行时 state、memory |
| `email-agent/USER_PROFILE.md` | 用户画像 |
| `email-agent/USER_HABITS.md` | 行为习惯 |
| `email-agent/WRITING_STYLE.md` | 写作风格 |
| `email-agent/UNSUBSCRIBE_STATE.json`（如果启用）| 订阅治理状态 |

> `UNSUBSCRIBE_STATE.json` 默认落在 `email-agent/` 下，compose 中没有显式挂载；生产部署建议加一条挂载或用 `UNSUBSCRIBE_STATE_PATH` 重定向到 `/app/data/...`。

---

## 扩展建议

- **反向代理**：生产环境在 `oo-chat` 前加 nginx/Traefik 做 TLS。
- **日志**：两个容器都 `print` 到 stdout，用 `docker compose logs -f email-agent` 跟踪。
- **资源限制**：Python agent 每次 LLM 调用都占一次并发，建议给 `email-agent` 配 `cpus` / `mem_limit`，避免单次爆峰影响宿主。
- **CI**：`make backend-agent-test` 可以在 Compose 外直接跑，不依赖 oo-chat。
