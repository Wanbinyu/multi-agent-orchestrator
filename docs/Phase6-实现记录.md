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
