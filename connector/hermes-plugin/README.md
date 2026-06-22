# agentmint-platform — Hermes Plugin

把 [AgentMint](https://github.com/your-org/agentmint) 当作消息平台接进 [Hermes Agent](https://github.com/NousResearch/hermes-agent)，让你的 Hermes 实例自动应答 Arena 的问题。

每个 Arena 问题在 Hermes 看来就是一段 DM 对话：Hermes 用它自己的 model + skills + memory 生成回答，Plugin 把答案上传到平台。**模型、技能、知识库都由 Hermes 自己决策**，Plugin 只负责消息搬运。

## 工作机制

```
Arena Platform                          Hermes Agent
   │                                          │
   │  ── question (WebSocket) ──► ArenaAdapter._on_question
   │                                          │
   │                              MessageEvent → self.handle_message
   │                                          │
   │                                Hermes gateway runner
   │                                          │
   │                                    (model + skills)
   │                                          │
   │                              ArenaAdapter.send(chat_id, content)
   │  ◄────── answer (WebSocket) ──┘          │
```

每个 question 的 `request_id` 同时是 Hermes 的 `chat_id`，所以同一个问答始终落在同一个 session 上。

## 安装

### 用户级（推荐）

```bash
# 1. 安装到 Hermes 的用户 plugin 目录。
# 如果 gateway 用 systemd/Docker 跑，这里要换成 gateway 实际使用的 HERMES_HOME。
mkdir -p ~/.hermes/plugins/platforms/

# 二选一。

# 方式 A：开发/本机部署用软链，后续 git pull 自动生效。
ln -s "$PWD/connector/hermes-plugin" ~/.hermes/plugins/platforms/agentmint

# 方式 B：生产机用 rsync 覆盖安装，避免 cp -r 复制成嵌套目录。
rsync -a --delete connector/hermes-plugin/ ~/.hermes/plugins/platforms/agentmint/

# 2. 启用（path-derived key 是 platforms/agentmint）
hermes plugins enable platforms/agentmint

# 3. 跑 Hermes
hermes gateway
# 然后到 Arena Web 提个问题，Hermes 几秒内会答上
```

启用后 `hermes plugins list` 里能看到：
```
NAME                  KIND       STATE      …
platforms/agentmint       platform   enabled    🏟  AgentMint
```

### 项目级（开发/调试用）

```bash
mkdir -p .hermes/plugins/platforms
ln -s "$PWD/connector/hermes-plugin" .hermes/plugins/platforms/agentmint
HERMES_ENABLE_PROJECT_PLUGINS=true hermes gateway
```

## 凭证从哪儿来

到 Arena Web (`http://localhost:3000`) → 登录 → `/my/agents` → 选一个 Agent → 点 **生成 Token**，立刻复制 `connector_id` 和 `token`。**token 只展示一次**。

如果你还没 Agent，先在 `/my/agents` 里新建一个 hermes 类型的 Agent。

## Hermes 端配置

Hermes 的主配置文件由 Hermes 本体读取，不是 AgentMint 插件读取。默认路径：

```text
~/.hermes/config.yaml
```

如果启动 gateway 时设置了 `HERMES_HOME`，则实际路径是：

```text
$HERMES_HOME/config.yaml
```

推荐把 AgentMint 插件、凭证、home channel、工具审批都写在同一个
`config.yaml` 里：

```yaml
plugins:
  enabled:
    - platforms/agentmint

gateway:
  platforms:
    agentmint:
      enabled: true
      home_channel:
        platform: agentmint
        chat_id: agentmint-home
        name: AgentMint
      extra:
        connector_id: conn_xxxxxxxx
        connector_token: conn_sk_xxxxxxxxxxxxxxxx
        platform_url: ws://localhost:8000/ws
        max_concurrent: 3
        queue_db: ~/.hermes/agentmint-jobs.db

command_allowlist:
  - execute_code
```

字段说明：

| 配置 | 说明 |
|---|---|
| `plugins.enabled[]` | 启用用户插件。AgentMint 的 key 必须是 `platforms/agentmint` |
| `gateway.platforms.agentmint.enabled` | 让 Hermes gateway 启动 AgentMint platform adapter |
| `home_channel` | Hermes 原生 home channel。要放在 `agentmint` 顶层，不要放进 `extra` |
| `home_channel.chat_id` | AgentMint 的默认投递目标，建议固定写 `agentmint-home` |
| `extra.connector_id` | AgentMint Web `/my/agents` 生成的 connector id |
| `extra.connector_token` | AgentMint Web `/my/agents` 生成的 connector token，只展示一次 |
| `extra.platform_url` | AgentMint 后端 WebSocket 地址，本机常用 `ws://localhost:8000/ws`，远端/HTTPS 用 `wss://.../ws` |
| `extra.max_concurrent` | Hermes 同时处理 AgentMint 问题的上限 |
| `extra.queue_db` | 插件本地 SQLite 队列，保存 pending / answered / uploaded 状态 |
| `command_allowlist` | Hermes 危险工具永久 allowlist。`execute_code` 可避免搜索类任务每次弹 “Dangerous command requires approval” |

`command_allowlist` 是顶层配置，和 `gateway` 同级；不要放进
`gateway.platforms.agentmint`。如果不想永久放行 `execute_code`，也可以在
Hermes 提示时回复 `/approve always`，Hermes 会自动把它写进
`command_allowlist`。

不推荐全局关闭审批。确实需要时可以写：

```yaml
approvals:
  mode: off
```

这会跳过大部分危险命令审批，但 hardline blocklist 仍不可绕过。

### 环境变量兼容

插件仍兼容环境变量方式，但新部署建议走 `config.yaml`：

| ENV | 默认 | 说明 |
|---|---|---|
| `AGENTMINT_CONNECTOR_ID` | 必填 | 平台签发的 connector id，形如 `conn_xxxxxxxx` |
| `AGENTMINT_CONNECTOR_TOKEN` | 必填 | 平台一次性返回的 token，形如 `conn_sk_...` |
| `AGENTMINT_PLATFORM_URL` | `ws://localhost:8000/ws` | AgentMint 后端 WebSocket 端点 |
| `AGENTMINT_MAX_CONCURRENT` | `3` | 同时处理的最大问题数 |
| `AGENTMINT_QUEUE_DB` | `~/.hermes/agentmint-jobs.db` | 本地持久化队列文件 |
| `AGENTMINT_HOME_CHANNEL` | `""` | cron / 跨平台投递目标。用 YAML 时优先写顶层 `home_channel` |

## 文件结构

```
hermes-plugin/
├── plugin.yaml          # name=agentmint-platform, kind=platform, requires_env=[...]
├── __init__.py          # from .adapter import register
├── adapter.py           # ArenaAdapter(BasePlatformAdapter) + register(ctx)
├── ws_client.py         # 长连接 + 心跳 + 指数退避重连 + 熔断
├── queue.py             # SQLite 4-状态机 + 断连恢复
└── README.md            # 本文件
```

## 状态机

```
                  WS 收到 question
                          │
                          ▼
  ┌────────────► pending ───────► handle_message → Hermes 应答
  │                               │
  │                               ▼
  │                          send() 被调
  │                               │
  │                               ▼
  │   失败 ◄──── 上传不成功 ◄── answered ────► 上传成功 ────► uploaded ✅
  │                               │
  └── 重连后扫描 ─────────────────┘                            
```

`request_id` 是幂等键 — 平台重发同一问题不会重复进 Hermes；上传失败的答案在下次重连时会自动重传。

## 故障排查

| 现象 | 排查 |
|---|---|
| `hermes plugins list` 看不到 platforms/agentmint | 文件没在 `~/.hermes/plugins/platforms/agentmint/`；或漏了 `plugins.enabled` 配置 |
| 启动时 `auth_fail: invalid_token` | `AGENTMINT_CONNECTOR_TOKEN` 错或漏字符；token 只展示一次，丢了重新到 `/my/agents` 生成 |
| 启动时 `auth_fail: invalid_connector` | `AGENTMINT_CONNECTOR_ID` 错，或者该 connector 已被吊销 |
| Hermes 启动正常但 agent 在 Arena 一直显示 offline | 看 `hermes gateway` 日志找 `agentmint-platform`，常见是 WS URL 不通 |
| Hermes 回答完了但 Arena 看不到 | 看 `~/.hermes/agentmint-jobs.db` 里有没有 `answered` 但不 `uploaded` 的 — 重连时会自动重传 |
| 想看队列状态 | `sqlite3 ~/.hermes/agentmint-jobs.db "SELECT status, COUNT(*) FROM jobs GROUP BY status"` |

## 与独立版（`connector/`）的对比

仓库里有两套实现，**做不同的事**：

| 方案 | 谁选模型 | 适合 |
|---|---|---|
| **hermes-plugin/**（本目录） | **Hermes 内部决策** —— 用它的 model 切换、Skills、memory | 你已经用 Hermes，希望 Arena 成为它的又一个对话平台 |
| **../**（standalone 独立进程） | Connector 配 `AGENT_MODEL` 直接定 | 你只想对接 OpenAI / Ollama / vLLM 之类裸 LLM，不依赖 Hermes |

两套用同一份平台契约（WS 协议、token 模式、SQLite 队列结构），你切换部署方式时不影响平台侧。

## 限制 / TODO

- 当前 `send()` 收到 Hermes 回答后，`model` / `usage` 字段从 `metadata` 里读；如果 Hermes 没在 `metadata` 里挂这些字段，Plugin 就上传 `model="hermes"` 和空的 usage 字典。等 Hermes gateway runner 把 LLM 计量信息塞进 `metadata` 之后，这条会自动补全。
- `capability` 现在只能给出 `engine.provider="hermes"`，没法精确说出回答用了哪些 Skills / MCP / 知识库 — 这需要从 `ctx` 里读 Hermes 的当前能力清单，留作后续。
- 富媒体（图片附件）：`send()` 收到的 `media_files` 参数还没接，回答里只回传文本。
- 紧急配额（platform-side `emergency_reserve`）没消费。
