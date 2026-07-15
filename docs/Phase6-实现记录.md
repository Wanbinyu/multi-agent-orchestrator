# Phase 6 实现记录

> 对标 Claude 差异的分阶段实现日志。每阶段完成后回归 `python -m pytest -q` 全绿。
> 起始：2026-07-13。

---

## Phase 6.0 - 工具注册表 + 网页工具 ✅

**目标**：统一工具注册与发现，新增网页搜索/抓取。

**新增文件**
- `src/tools/registry.py` - `ToolRegistry` 单例：装饰器注册、`build_instructions()` 生成提示词、`execute()` 统一执行、按 category 分类。
- `src/tools/web_tools.py` - `web_search`（DuckDuckGo，可选 duckduckgo-search）、`fetch_url`（urllib + html.parser 转 Markdown）。
- `tests/test_registry.py`、`tests/test_web_tools.py`

**修改**
- `src/tools/worker_tools.py` - 工具改用注册表装饰器；`execute_tool_call()` 委托 `tool_registry.execute()`。
- `src/tools/memory_tools.py` - 注册 `search_project_files`/`search_memory`。
- `src/core/agent.py` - `TOOL_INSTRUCTIONS` 常量替换为 `tool_registry.build_instructions()` + `TOOL_RULES`；`_build_permission_message()` 通用化。
- `src/core/worker.py` - `build_tool_instructions()` 改用注册表。
- `src/gateway/provider.py` - 移除 4 处 `path/content/command` 参数过滤，原生工具调用参数全透传。
- `src/cli/chat_command.py`、`src/ui/static/js/chat.js` - 工具展示通用化。
- `config/workers.yaml` - 为 architect/frontend_dev/backend_dev/tester 授予 web_search/fetch_url。

**结果**：237 passed。注册工具 7 个。

---

## Phase 6.1 - 上下文生存能力 ✅

**目标**：解决最关键短板--长会话撞上下文上限报错。

**新增文件**
- `src/core/token_counter.py` - token 计数（可选 tiktoken，无则字符估算）。
- `src/core/compactor.py` - `ContextCompactor`：超阈值（默认 75% 窗口）时把旧消息总结为摘要**真正替换历史**。
- `tests/test_token_counter.py`、`tests/test_compactor.py`

**修改**
- `src/models/schemas.py` - `ModelConfig.max_context_tokens` 字段。
- `src/core/agent.py` - `__init__` 加 `max_context_tokens`/`compaction_threshold`；`_maybe_compact_context()` 在 `run_turn`/`run_turn_stream` 每轮前调用（async 路径用 `asyncio.to_thread`）。

**机制**：与 Claude Code 一致--LLM 摘要压缩（非向量化）。保留 system + 最近 N 轮 + 摘要消息。

**结果**：250 passed。

---

## Phase 6.2 - 工具增强 ✅

**目标**：补齐高频工具，减少整文件重写。

**新增文件**
- `src/tools/paths.py` - 共享 `resolve_path`（解决循环导入）。
- `src/tools/search_tools.py` - `glob_files`（通配符递归）、`grep_content`（正则搜内容+行号）。
- `tests/test_search_tools.py`

**修改**
- `src/tools/worker_tools.py` - 新增 `edit_file`（精确替换，校验唯一性）。

**结果**：265 passed。注册工具 10 个。

---

## 本地 LLM 接入 + 扩展点 ✅

**目标**：让 MAO 能用本地 LLM；为未来功能预留扩展点。

**新增文件**
- `src/gateway/local_provider.py` - `OllamaProvider`（复用 OpenAI 兼容）、`LocalLlamaCppProvider`（进程内 GGUF，懒加载，可选依赖）。
- `src/tools/tool_sources.py` - `ToolSource` 协议 + `MCPToolSource` 占位（Phase 6.4 实现）。
- `config/providers.yaml.example` - Ollama/llamacpp 配置示例。
- `tests/test_local_provider.py`、`tests/test_tool_sources.py`
- `docs/本地LLM接入与扩展点.md`

**修改**
- `src/models/schemas.py` - `ProviderConfig.type` 扩展 `ollama`/`llamacpp`；新增 `extra: dict` 字段。
- `src/gateway/provider.py` - `create_provider()` 支持新类型。
- `src/tools/registry.py` - `ToolSource` 协议、`add_source()`、外部源发现/执行（本地同名优先）。

**扩展点预留**：ToolSource（MCP 槽位，已建）、EmbeddingProvider/HookRegistry/SubagentSpawner/NativeToolAdapter（未建，等用到再建）。

**结果**：284 passed。

---

## Phase 6.3 - 原生 tool_use ✅

**目标**：让支持 `tool_use` 的模型走原生结构化工具调用（仿 Claude Code），其余模型保留 Markdown 兜底。

**机制**：原生模式启用时，工具定义经 `tools=` 参数传入；模型返回的 `tool_use` 由 Provider 归一化为 Markdown 块（Phase 6.0 已实现），Agent 统一解析执行。assistant 消息以纯文本（Markdown 扁平化）存入历史，因此 Anthropic/OpenAI 的 tool_result 语义自然满足，无需重构消息结构。

**新增文件**
- `tests/test_native_tool_use.py` - schema 生成、原生模式检测、系统提示、tools 透传（13 项）。
- `src/tools/contrib/__init__.py` + `src/tools/contrib/example_tools.py` - 第三方工具示例（`word_count`）。
- `docs/工具开发指南.md` - 面向开发者的工具开发完整指南。

**修改**
- `src/tools/registry.py` - `build_tool_schemas(provider_type, tool_names)` 生成 Anthropic/OpenAI 原生 schema；`_build_input_schema()` 转 JSON Schema（有 default 的参数不入 required）。
- `src/models/schemas.py` - `ModelConfig.native_tools: bool | None`（None=按 capabilities 自动）。
- `src/gateway/provider.py` - Anthropic/OpenAI 的 `chat()`/`chat_stream()` 接收并透传 `tools` kwarg。
- `src/core/agent.py` - `TOOL_RULES_NATIVE` 常量；`_should_use_native_tools()`（含 isinstance 防御）、`_provider_type()`、`_get_native_tools()`、`_native_kwargs()`；`_build_system_prompt()` 原生模式跳过 Markdown 工具列表；4 处 gateway 调用追加 `**self._native_kwargs()`。
- `src/tools/worker_tools.py` - import contrib 示例工具触发注册。

**结果**：297 passed。注册工具 11 个。原生模式对声明 `tool_use` 的模型自动启用，可经 `native_tools` 配置强制开关。

---

## 扩展：第三方工具开发支持 ✅

- `src/tools/contrib/` 目录 + `word_count` 示例工具。
- `docs/工具开发指南.md`：装饰器注册、params schema、category 与权限、ToolSource 外部源、测试范式、检查清单。
- 第三方工具 import 即注册，CLI/Web/原生三端自动可用。

---

## Phase 6.4 - 扩展生态（Hooks + MCP）✅

**目标**：接入工具调用前后钩子与 MCP 外部工具服务器。

### Hooks（工具调用拦截）

**新增文件**
- `src/core/hooks.py` - `HookRegistry`、`HookAbort`、`AuditLogHook`、`load_hooks_from_config()`。
- `tests/test_hooks.py`

**机制**：
- `pre_hook(tool_name, params) -> dict | None`：返回 dict 改写参数；返回 None 保持；抛 `HookAbort` 阻止执行。
- `post_hook(tool_name, params, result) -> ToolResult | None`：返回 ToolResult 改写结果。
- 钩子异常不中断主流程（容错）。
- `ToolRegistry.execute()` 在执行前后调用 hooks；对外部源工具同样生效。
- 内置 `AuditLogHook` 写审计日志；`audit_pre`/`audit_post` 模块级函数可经 config 加载。

### MCP 适配器（外部工具服务器）

**新增文件**
- `src/tools/mcp_adapter.py` - `MCPToolSource`、`_AsyncLoopRunner`、`load_mcp_sources_from_config()`。
- `tests/test_mcp_adapter.py`

**机制**：
- 支持 stdio（command/args/env）与 sse（url）两种传输。
- MCP 是异步协议，用独立线程事件循环（`_AsyncLoopRunner`）桥接为同步调用，可在同步与异步上下文使用。
- 连接懒加载、常驻保持、`shutdown()` 释放。
- `mcp` 包可选；未安装时 `list_tools()` 返回空、`execute()` 返回清晰错误，不影响其他功能。
- MCP 工具注册后与内置工具统一发现/执行，并受 Hooks 拦截。

### 启动加载与配置

**新增文件**
- `src/tools/extensions.py` - `load_extensions(config_dir)`：幂等加载 hooks.yaml + mcp.yaml 到全局 `tool_registry`。
- `tests/test_extensions.py`
- `config/hooks.yaml.example`、`config/mcp.yaml.example`

**修改**
- `src/tools/registry.py` - 新增 `hooks` 属性、`add_pre_hook`/`add_post_hook`、`execute()` 拆分 `_execute_raw()` 注入 hooks。
- `src/tools/tool_sources.py` - 从占位改为 re-export 真实 `MCPToolSource`。
- `src/cli/chat_command.py` - `run_chat_loop` 启动时 `load_extensions()`。
- `src/ui/app.py` - lifespan 启动时 `load_extensions()`。

**结果**：329 passed。

---

## Phase 6.5 - 故障转移与协作稳定性收口 ✅

**背景**：真实项目任务暴露出目录探查失败、正文代码被保存为 `generated_N`、协作漏判和 429 后无法完整回退等问题。断电后对未提交工作区进行完整性审计，并按真实配置形状补齐实现与测试。

### Gateway

- fallback 按每个模型的 `fallback_models` 递归展开并去环，支持 `glm-ark -> kimi-for-coding -> glm-chat`。
- 认证错误、请求参数错误、模型不可用、配额和连接错误分开处理；`invalid max_tokens` 不再误触发故障切换。
- 配额冷却优先读取 `Retry-After`，并解析 `5-hour` / minutes / seconds 时间窗口。
- 冷却中的主模型被跳过时也发送 failover 事件。
- `/test-models` 走 Provider 正式调用路径，统一 Coding Plan Bearer 鉴权，失败/成功会更新或清除健康状态；命令明确提示少量 token 消耗。

### Agent / Worker / 文件产出

- 新增跨平台 `list_dir`；`glob_files` 增加独立 `path` 搜索根目录参数。
- 项目类关键字先行触发协作，减少复杂任务漏判。
- Worker 增加最多 5 轮工具循环，工具结果回填模型后继续执行。
- 旧 Worker 配置已授予读取能力时，自动补齐 `list_dir` / `glob_files` / `grep_content` / `read_file`。
- Worker 严格校验工具授权，原生 `tool_use` 与 Markdown 模式共用白名单。
- 原生模式不再注入 Markdown 工具说明，避免双协议冲突。
- Agent / Worker / Reviewer 不再把正文代码块自动保存为 `generated_N`。
- 需要文件但只返回代码块时，Worker 会要求模型改用 `write_file`；再次失败则保存 `content.txt` 并将任务标记失败。
- CLI 启动页改为简洁提示；输入 `/` 显示命令候选和说明，继续输入按前缀实时过滤，`/help` 保留完整列表。

### 验证

- 新增或扩展：`tests/test_gateway_failover.py`、`tests/test_connection_test.py`、`tests/test_worker.py`、`tests/test_worker_e2e.py`、`tests/test_chat_router_stream.py`、`tests/test_chat_command_mode.py`、`tests/test_agent_fixes.py`、`tests/test_search_tools.py`。
- `python -m compileall -q src tests scripts` 通过。
- `python scripts/demo_failover.py` mock 演示通过，使用系统临时目录，不写用户会话。
- 全量回归：**374 passed**（仅保留 FastAPI/Starlette 测试客户端弃用警告）。

详细根因与剩余限制见 `docs/故障修复与稳定性收口记录.md`。

---

## Phase 6.6 P0 - CLI 结果可见性与过程反馈 ✅

**背景**：真实项目分析任务读取数十个文件后，CLI 只打印原始 `Read(...)` 调用清单和 `response.md` 路径。模型已经生成最终方案，但工具 spinner 覆盖了最后一轮内容，非协作分支没有重新渲染 `assistant_message`。

### 事件协议与 Agent

- `ChatStreamEvent` 新增 `tool_start`、`tool_complete` 和通用 `tool_call` payload。
- Agent 在实际执行工具前后发送结构化进度事件；拒绝、参数解析失败和执行失败均进入完成事件。
- Markdown 与原生 `tool_use` 最终都归一到相同的 CLI 事件和汇总路径。
- Agent 规则明确要求工具结束后输出检查范围、关键发现、建议/下一步和交付文件，禁止以工具调用作为最后输出。

### CLI 展示

- 工具过程按“探索项目 / 检索代码 / 查询资料 / 生成交付物 / 执行验证”组织。
- 每阶段只展开前 4 项，后续同类操作折叠，避免几十行 `Read(...)` 刷屏。
- spinner 实时显示已分析的目录、文件、检索、命令或写入数量。
- “本轮工作”面板汇总唯一目录/文件、重复操作、成功数、失败数及前三个失败原因。
- 修复单 Agent 使用工具后最终答案不显示的问题；固定展示最终答案和交付文件。
- 旧的 `Update(未知文件) 0 行` 通用兜底不再作为最终汇总形式。

### WebUI 同期优化

- 顶部标题和导航压缩为应用工作台结构，桌面对话区在 1280px 视口下由约 572px 扩大到约 964px。
- 上下文默认折叠；中等宽度和移动端改为带遮罩的抽屉。
- 移动端聊天使用 `100dvh` 剩余空间，会话列表横向滚动，输入区保持可见。
- 配置页取消双层滚动，字段按服务连接、认证运行、模型映射分组。
- 移动端模型表转换为纵向卡片，390px 视口无横向溢出。
- 新建会话使用应用内对话框；历史空标题显示为“未命名会话”。
- 静态 CSS/JS 增加版本参数，避免升级后继续命中旧缓存。

### 验证

- 新增 `tests/test_chat_command_output.py`，扩展 `tests/test_agent_stream.py` 和 `tests/test_chat_command_mode.py`。
- JavaScript 语法、Python 编译和 `git diff --check` 通过。
- WebUI 在 `1280x720`、`390x844` 下完成配置页、聊天页、上下文抽屉和新建会话交互验收，控制台无错误。
- 全量回归：**376 passed**（仅保留 FastAPI/Starlette 测试客户端弃用警告）。

### 未完成

- `project_tree` 工具与零 token `/tree` 命令。
- 项目审查固定输出精简目录树。
- Web 可折叠项目文件树。
- 单轮只读工具缓存和项目索引复用；当前过程汇总会报告重复读取，但不会减少其 token 消耗。
