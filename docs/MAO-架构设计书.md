# MAO 架构设计书

**项目**：multi-agent-orchestrator  
**作用**：一个多模型 Agent 编排工具，支持一次性任务拆分执行，也支持持续对话中的工具调用与多模型协作。  
**更新方式**：每完成一部分，就在下方对应条目把 `- [ ]` 改成 `- [x]`，并补全实现细节。

---

## 1. 项目定位

MAO（Multi-Agent Orchestrator）把一个大需求拆成多个子任务，分配给不同专长的模型并行/串行执行，最后由 Reviewer 整合。同时提供 `/chat` 持续对话模式，让用户像使用 Claude Code 一样通过自然语言读文件、写文件、执行命令。

---

## 2. 技术栈

| 层级 | 技术 | 说明 |
|---|---|---|
| 语言 | Python 3.11+ | 主开发语言 |
| CLI 框架 | Typer | `run.py` 子命令 |
| Web 框架 | FastAPI + Uvicorn | 配置 UI 与对话 API |
| 模板/前端 | Jinja2 + 原生 JS/CSS | 无前端构建链 |
| 模型 SDK | Anthropic SDK、OpenAI SDK | 兼容 Anthropic 与 OpenAI 兼容接口 |
| 数据模型 | Pydantic v2 | 配置、消息、事件模型 |
| 持久化 | YAML、.env | 会话、Provider、Worker 配置均本地存储 |
| CLI 交互 | prompt_toolkit、rich、questionary | 颜色输出、交互提示、Shift+Tab 模式切换 |
| 测试 | pytest | 单元测试覆盖核心路径 |

---

## 3. 目录结构

```
multi-agent-orchestrator/
├── config/                 # 运行时配置（Provider、Worker）
│   ├── providers.yaml
│   └── workers.yaml
├── sessions/               # 会话持久化
│   ├── <id>.yaml
│   └── <id>/output/        # 该会话的输出文件
├── docs/                   # 设计文档与记录
├── scripts/
│   └── run_ui.py           # 一键启动 Web UI
├── src/
│   ├── cli/                # CLI 命令与向导
│   │   ├── agent_setup.py
│   │   ├── chat_command.py
│   │   ├── provider_presets.py
│   │   └── setup_wizard.py
│   ├── core/               # 核心编排与对话
│   │   ├── agent.py        # 对话 Agent（流式、工具循环、权限门控）
│   │   ├── dispatcher.py   # 任务调度器
│   │   ├── orchestrator.py # 总指挥：拆任务
│   │   ├── reviewer.py     # 审查与收口
│   │   ├── session.py      # 会话模型与存储
│   │   └── worker.py       # Worker 执行子任务
│   ├── gateway/            # 模型调用网关
│   │   ├── client.py       # GatewayClient：统一入口、计费、主模型选择
│   │   ├── provider.py     # AnthropicProvider / OpenAICompatibleProvider
│   │   ├── router.py       # 模型路由与 Provider 轮询
│   │   └── connection_test.py
│   ├── models/             # 共享数据模型
│   │   ├── catalog.py      # 模型目录
│   │   └── schemas.py      # Pydantic 模型
│   ├── tools/              # 工具实现
│   │   ├── file_tools.py
│   │   └── worker_tools.py
│   └── ui/                 # Web UI
│       ├── app.py
│       ├── config_manager.py
│       ├── presets/        # Provider 预设（模块化）
│       ├── routers/
│       │   ├── chat.py
│       │   └── providers.py
│       ├── static/
│       └── templates/
├── tests/                  # 单元测试
├── run.py                  # CLI 入口
├── requirements.txt
└── .env                    # API Key（本地，不提交）
```

---

## 4. 核心架构

### 4.1 入口层

- `run.py`：Typer 应用，提供 `setup`、`agent-setup`、`chat`、`run` 子命令。
- `scripts/run_ui.py`：启动 FastAPI Web 服务，默认监听 `127.0.0.1:8123`。

### 4.2 网关层（Gateway）

`src/gateway/client.py` 的 `GatewayClient` 是模型调用的统一入口：

- 读取 `config/providers.yaml`，加载启用的 Provider 与模型。
- 维护 `Billing` 实例，汇总每次调用的 token 与成本。
- 提供 `chat_with_main_model()` / `chat_with_main_model_stream()`。
- 提供 `chat()` / `chat_stream()` 供 Worker/Orchestrator/Reviewer 按指定模型调用。

`src/gateway/provider.py` 实现两种 Provider：

- `AnthropicProvider`：原生 Anthropic Messages API，支持流式。
  - **按端点自动选择鉴权方式**：火山引擎 Coding Plan 端点（`/api/coding`）用 Bearer（`auth_token`），其它 Anthropic 兼容端点用 `x-api-key`（`api_key`）。
  - **Coding Plan Token 来源**：优先环境变量 `ANTHROPIC_AUTH_TOKEN`，回退到 `.env` 的 `ARK_CODING_TOKEN`。
  - **原生工具调用兼容**：把模型返回的 `tool_use` 块统一转成 Markdown 工具块（` ```tool:xxx `），同时跳过 `thinking` 块不注入正文。
  - **请求体清洗**：发往 API 前清除孤立代理字符（surrogate），避免 SDK 编码失败。
- `OpenAICompatibleProvider`：兼容 OpenAI 协议的接口（DeepSeek、Ark、GLM、Kimi 等），支持流式。
  - 同样把原生 `tool_calls` 转成 Markdown 工具块，兼容 `reasoning_content`。

`src/gateway/router.py` 负责：

- 按模型名找到可用 Provider。
- 多个 Provider 轮询/ fallback，处理 RPM 限制与失败重试。

### 4.3 模型层（Models）

`src/models/schemas.py` 定义核心数据结构：

- `ProviderConfig`、`ModelConfig`、`WorkerConfig`
- `ChatMessage`、`ChatResponse`、`StreamChunk`、`ChatStreamEvent`
- `Task`、`TaskPlan`、`TaskResult`
- `ApprovalMode`、`PermissionRequest`

`src/models/catalog.py` 维护可用模型列表。

### 4.4 编排层（Orchestrator / Dispatcher / Worker / Reviewer）

用于一次性任务 `python run.py <需求>` 或 `/chat` 中的自动协作。

```
用户请求
  ↓
Orchestrator.plan()      # 拆成子任务
  ↓
Dispatcher.dispatch()    # 按依赖调度、并发执行
  ↓
Worker.execute()         # 每个子任务调用对应模型 + 工具
  ↓
Reviewer.review()        # 审查、整合、输出最终结论
```

- **Orchestrator**：总指挥，把需求拆成带依赖的 `TaskPlan`。
- **Dispatcher**：根据 `depends_on` 做拓扑排序，并发执行无依赖任务。
- **Worker**：每个 Task 的实际执行者，根据任务类型选择模型、构造 system prompt、调用工具。
- **Reviewer**：读取所有 TaskResult，判断通过/不通过，给出最终整合输出。

### 4.5 对话层（Session / Agent）

`src/core/session.py`：

- `Session`：多轮对话会话，YAML 持久化。
- `SessionStore`：CRUD、按时间倒序列出。
- 每个会话有独立 `output_dir`，文件写入默认在此目录。
- `approval_mode` 按会话保存：新建会话默认 `"approve"`，模型默认值 `"auto"` 保证测试兼容。

`src/core/agent.py`：

- `Agent.run_turn()`：同步版一轮对话，供旧接口使用。
- `Agent.run_turn_stream()`：流式版，产出 `ChatStreamEvent`。
- 工具循环：最多 `max_tool_iterations` 轮，直到模型不再输出工具块。
- **工具调用解析**：`_parse_tool_calls` 兼容三种闭合方式：标准 ` ``` `、编码模型特殊 token `<|tool_calls_section_end|>`、字符串结尾；`_strip_toolcall_artifacts` 清除残留特殊 token。
- 权限门控：
  - `readonly`：直接拒绝。
  - `approve`：`yield permission_request` + `asyncio.Event` 等待用户响应。
  - `auto`：直接执行。
- 自动落盘：仅在 `auto` 模式下写 `response.md`；多模型协作时 Reviewer 最终输出的代码块也会落盘。

### 4.6 工具层

`src/tools/worker_tools.py`：

- `read_file`
- `write_file`：**绝对路径直接写入**，相对路径才做目录穿越校验。
- `run_command`（白名单前缀）

`src/tools/file_tools.py`：

- `write_output_files`：从 Markdown 代码块推断文件名并写入。
- `write_text_file`：写任意文本文件。

### 4.7 Web UI

`src/ui/app.py`：FastAPI 应用，挂载静态资源、Jinja2 模板、路由。

路由：

- `/`：Provider 配置页（`src/ui/routers/providers.py`）。
- `/chat`：对话页（`src/ui/routers/chat.py`）。
- `/api/chat/sessions/*`：会话 API。
- `/api/providers/*`：Provider API。

前端：

- `chat.js`：SSE 消费、模式切换、权限卡片、协作面板。
- `app.js`：Provider 配置表单、连接测试、预设选择。

### 4.8 CLI

- `agent_setup.py`：新版 Provider 配置向导。
- `setup_wizard.py`：旧版 Worker 配置向导。
- `chat_command.py`：交互式对话 REPL，支持 Shift+Tab 切换模式、`/mode` 命令、终端权限确认。

---

## 5. 数据流

### 5.1 一次性任务流

```
run.py run "开发一个登录页面"
  ↓
GatewayClient
  ↓
Orchestrator.plan("开发一个登录页面")
  → TaskPlan { summary, tasks[] }
  ↓
Dispatcher.dispatch(plan)
  → 拓扑排序，并发执行
  ↓
Worker.execute(task)
  → 调用指定模型，可能使用工具
  → TaskResult
  ↓
Reviewer.review(request, plan, results)
  → Review { passed, issues, final_output }
  ↓
输出文件 + summary.md + 计费信息
```

### 5.2 持续对话流

```
/chat 用户输入
  ↓
Agent.run_turn_stream(user_input)
  ↓
_should_collaborate(user_input)?
  ├─ 是 → _run_collaboration_stream()
  │         → plan / task_start / task_complete / review_complete / done
  └─ 否 → 主模型单轮/工具循环
            → delta / permission_request / done
  ↓
CLI 或 Web 消费事件
```

### 5.3 流式与 SSE

- Provider 层返回异步生成器 `StreamChunk`。
- `GatewayClient` 包装为异步流。
- `Agent.run_turn_stream()` 消费并转换为 `ChatStreamEvent`。
- Web 端通过 `StreamingResponse` 以 `text/event-stream` 返回。
- CLI 端直接 `async for` 消费并打印。

---

## 6. 配置与持久化

| 文件 | 内容 | 写入方式 |
|---|---|---|
| `config/providers.yaml` | Provider 列表、API Key 占位、模型映射、main_model | Web UI 或 `agent_setup` |
| `config/workers.yaml` | Worker 角色定义 | `setup` 向导 |
| `sessions/<id>.yaml` | 会话元数据、消息历史、approval_mode | `SessionStore.save()` |
| `sessions/<id>/output/` | 会话产生的文件 | 工具写入 |
| `.env` | 真实 API Key / Token | 用户手动或向导写入 |

API Key 只保存在本地 `.env`，前端编辑 Provider 时留空表示保持不变。

### 当前生效配置（2026-07-12）

- `main_model`：`glm-ark`（火山引擎 `ark-code-latest`，Anthropic 兼容 `/api/coding` 端点）。
- `.env` 关键变量：
  - `ARK_CODING_TOKEN`：火山引擎 Coding Plan Token（Bearer 鉴权），主用。
  - `ARK_API_KEY` / `VOLCENGINEARK_API_KEY`：普通 Ark Key，仅 `/api/v3` 可用，不能用于 Coding Plan。
  - `KIMI_API_KEY` / `KIMI1_API_KEY`：Kimi 转发 Key（有额度限制）。
- Provider 鉴权规则：`/api/coding` 端点用 Bearer（`auth_token`，优先 `ANTHROPIC_AUTH_TOKEN` 环境变量），其它 Anthropic 端点用 `x-api-key`。
- 切换主模型：编辑 `config/providers.yaml` 的 `main_model` 字段即可，可选值见 `models` 段（`glm-ark`、`glm-chat`、`glm`、`kimi-for-coding`）。

---

## 7. 权限模式架构

```
用户输入
  ↓
Agent.run_turn_stream()
  ├─ 主模型输出工具块
  ├─ _parse_tool_calls()
  │     ├─ readonly → 拒绝
  │     ├─ approve  → yield permission_request
  │     │              → asyncio.Event 等待
  │     │              → respond_to_permission(request_id, approved)
  │     │              → approved 为真才执行
  │     └─ auto     → 直接执行
  ↓
CLI：终端 y/n 提示
Web：权限卡片 Approve/Deny
```

Web 后端用内存 `active_agents: dict[str, Agent]` 保存当前正在流式响应的 Agent，以便权限响应端点能正确路由。

**协作路径的前置批量确认**：多模型协作（`_run_collaboration_stream`）在 `plan` 事件后、dispatch 前，`approve` 模式下会 yield 一个 `permission_request`（`tool="collaboration"`，含子任务数与输出目录），一次性征求用户同意：

- 批准 -> 子任务自动执行（不再逐条确认）。
- 拒绝 -> `done` 提示“协作已取消”，不 dispatch。
- `readonly` -> 不触发协作。
- `auto` -> 直接执行。

`/plan` chat 命令与 `run.py run` 同样在执行前确认：`readonly` 跳过、`approve` 终端 y/n、`auto`/非交互（`--yes` 或非 TTY）直接执行。

---

## 8. 多模型协作架构

`/chat` 中主模型先判断请求复杂度：

- 闲聊、单文件读写 → 单模型直接回答。
- 开发功能/页面/API/多步骤实现 → 触发协作。

协作流程复用 `Orchestrator` → `Dispatcher` → `Worker` → `Reviewer`，并通过 SSE 事件向前端实时汇报进度。

---

## 9. 测试策略

- 单元测试覆盖每个核心模块：`tests/test_*.py`。
- 关键测试集：
  - `test_agent_permission.py`：权限模式。
  - `test_agent.py`：工具调用解析（含 `<|tool_calls_section_end|>` 闭合）、artifact 清洗。
  - `test_agent_stream.py`、`test_chat_router_stream.py`：流式对话。
  - `test_agent_collaboration.py`、`test_dispatcher_callback.py`：多模型协作。
  - `test_worker_tools.py`：绝对路径写入、目录穿越校验。
  - `test_ui.py`、`test_provider_model_map.py`：Web UI 与 Provider 配置。
- 当前状态：`177 passed`。
- 运行方式：

```powershell
python -m pytest -q
```

---

## 10. 部署与运行

```powershell
# 安装依赖
pip install -r requirements.txt

# 配置 Provider
python run.py agent-setup
# 或启动 Web UI 配置
python scripts/run_ui.py

# 一次性任务
python run.py "开发一个登录页面"

# 持续对话
python run.py chat

# Web 对话
python scripts/run_ui.py --no-open
# 浏览器打开 http://127.0.0.1:8123/chat
```

---

## 11. 模块完成度清单

每次做完一部分，就把对应 `- [ ]` 改成 `- [x]`，并在此文件末尾或对应 Phase 文档记录实现要点。

### Phase 1：Provider 连接配置

- [x] Provider 模型与配置持久化
- [x] 15+ 常用 Provider 预设与模块化扩展
- [x] Provider 增删改查 API
- [x] 连接测试
- [x] API Key 本地 `.env` 存储
- [x] 主模型选择
- [x] Web 配置 UI

### Phase 2：对话式交互

- [x] Session 多轮会话模型
- [x] SessionStore YAML 持久化
- [x] Agent 同步工具循环
- [x] CLI 交互式对话
- [x] Web 对话页与会话列表
- [x] Web 对话 API

### Phase 3：流式回答

- [x] StreamChunk / ChatStreamEvent 模型
- [x] Provider 流式实现
- [x] Gateway 流式方法
- [x] Agent 流式一轮
- [x] Web SSE 端点
- [x] 前端 SSE 消费与增量渲染
- [x] CLI 流式打印

### Phase 4：对话中的多模型自动协作

- [x] 主模型自动判断是否需要协作
- [x] 复用 Orchestrator / Dispatcher / Worker / Reviewer
- [x] 协作进度回调
- [x] 协作事件类型扩展
- [x] Web 协作面板
- [x] CLI 协作进度打印

### Phase 4.5：权限确认与 Shift+Tab 模式切换

- [x] ApprovalMode / PermissionRequest 数据模型
- [x] Agent 权限门控（readonly / approve / auto）
- [x] `respond_to_permission` + `asyncio.Event`
- [x] CLI Shift+Tab 切换与 `/mode` 命令
- [x] Web 模式指示器与切换端点
- [x] Web 权限卡片与响应端点
- [x] 活跃 Agent 内存映射
- [x] Provider 原生工具调用兼容（`tool_use` / `tool_calls` -> Markdown 工具块）
- [x] 工具调用解析兼容多种闭合（` ``` ` / `<|tool_calls_section_end|>`）
- [x] 火山引擎 Coding Plan Bearer 鉴权（`/api/coding` 端点）
- [x] 请求体 surrogate 清洗
- [x] 绝对路径写入放行
- [x] Worker 空内容判定失败 + 工具写入文件回填 `files_written`
- [x] 协作 Reviewer 最终输出自动落盘
- [x] 单元测试（177 passed）

### Phase 5：长期记忆与项目上下文

- [ ] 项目级 Memory 抽象
- [ ] 会话自动总结
- [ ] 项目文件索引与代码搜索工具
- [ ] 记忆注入上下文窗口
- [ ] UI 记忆/上下文侧边栏

### Phase 6：工具生态与外部集成

- [ ] 统一工具注册表
- [ ] 网页搜索 / URL 抓取工具
- [ ] 可选代码执行沙箱
- [ ] MCP 适配器
- [ ] 外部工具配置 UI
- [ ] 打包分发（可执行文件 / IDE 插件）

---

## 12. 已知限制与后续方向

1. Worker 子任务在协作中仍自动执行文件写入，未经过用户逐条确认。
2. 长期记忆尚未实现，跨会话需要重复交代背景。
3. 工具层目前只有本地文件和命令，缺少网页搜索、浏览器等外部能力。
4. 可进一步把 Agent 权限机制扩展到 `/plan` 一次性任务，让用户在协作开始前一次性确认。
5. `ark-code-latest` 是思考型模型，会先消耗思考 token 再输出正文；遇到额度或可用性波动需稍等重试。
6. 不同模型/代理对工具调用格式差异较大，目前兼容 Markdown 工具块 + 原生 `tool_use`/`tool_calls`，未来若接入新格式需扩展 `_parse_tool_calls`。
