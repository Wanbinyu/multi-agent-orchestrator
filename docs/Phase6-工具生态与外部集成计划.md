# Phase 6：工具生态与外部集成

## Context

Phase 5（长期记忆与项目上下文）已 100% 完成。下一步将进入 **Phase 6：工具生态与外部集成**，让 Agent 不再局限于本地文件与命令，能够访问外部信息、调用网页服务、接入更多工具。

## 进度

| 能力 | 状态 |
|---|---|
| 统一工具注册表 `src/tools/registry.py` | ✅ 已完成 |
| 网页搜索 `web_search` | ✅ 已完成 |
| URL 抓取 `fetch_url` | ✅ 已完成 |
| Agent / Worker / Provider 改为注册表驱动 | ✅ 已完成 |
| CLI / Web 工具展示通用化 | ✅ 已完成 |
| 流式重试去重 | ✅ 已完成 |
| 自动模型故障切换 | ✅ 已完成 |
| 协作 Worker 多轮工具循环 | ✅ 已完成 |
| 明确文件产出（禁止 generated_N） | ✅ 已完成 |
| Claude 风格 `/` 命令动态补全 | ✅ 已完成 |
| CLI 工具循环最终回答可见性 | ⏳ Phase 6.6 P0 |
| 项目树工具与 `/tree` 命令 | ⏳ Phase 6.6 P1 |
| Web 项目文件树 | ⏳ Phase 6.6 P2 |
| 代码执行沙箱 | ⏳ 计划中 |
| MCP 适配器（stdio / SSE） | ✅ 已完成，依赖可选 |
| UI 工具配置面板 | ⏳ 计划中 |

## Goal

扩展 Agent 的工具能力，建立统一的工具注册与管理机制，并接入外部高频工具：

1. **统一工具注册表**：`src/tools/registry.py` ✅
2. **内置高频工具**：
   - 网页搜索（DuckDuckGo，可选 `duckduckgo-search` 增强）✅
   - URL 抓取（获取网页内容并转换为 Markdown）✅
3. **可选增强**（后续迭代）：
   - 代码执行沙箱
   - 更多 MCP Server 预设与真实环境验证
   - IDE 插件 / VS Code 扩展
4. **UI 配置**（后续迭代）：在连接配置页增加外部工具 API Key / MCP 服务器设置。

## 已实现

### 统一工具注册表

`src/tools/registry.py` 提供 `ToolRegistry` 单例：

- 装饰器 `@tool_registry.register(name, description, params, category)` 注册工具。
- `build_instructions(tool_names=None)` 自动生成系统提示中的工具说明（Markdown 代码块示例）。
- `execute(name, params, base_dir, allowed_prefixes)` 统一执行，自动注入 `base_dir` / `allowed_prefixes`，异常兜底为 `ToolResult(success=False)`。
- 工具按 `category` 分类：`read` / `write` / `execute` / `external` / `unsafe`。

内置工具在 `src/tools/worker_tools.py` 导入时自动注册，共 12 个：`read_file`、`write_file`、`edit_file`、`run_command`、`list_dir`、`glob_files`、`grep_content`、`search_project_files`、`search_memory`、`web_search`、`fetch_url`、`word_count`。

### 网页工具 `src/tools/web_tools.py`

- `web_search(query, top_n=5)`：优先使用可选依赖 `duckduckgo-search`；未安装时降级为抓取 DuckDuckGo lite HTML 解析。返回 Markdown 列表（标题、链接、摘要）。
- `fetch_url(url, max_length=8000)`：用 `urllib` 抓取页面（限 1MB、设置 UA、处理 gzip），用 `html.parser` 抽取标题/正文/链接转成简易 Markdown。
- 两者 `category=external`，仅依赖标准库，无新强制依赖。
- 遵守权限模式：`readonly` 拒绝、`approve` 触发确认（与本地工具一致）。

### 接入点改造

- `src/core/agent.py`：`TOOL_INSTRUCTIONS` 常量替换为 `tool_registry.build_instructions()` + `TOOL_RULES`；`_build_permission_message()` 通用化，对任意工具展示 `path`/`command`/`url`/`query` 等关键字段。
- `src/core/worker.py`：`build_tool_instructions()` 改为调用注册表。
- `src/gateway/provider.py`：移除 4 处 `path/content/command` 参数过滤，原生 `tool_use` / `tool_calls` 的全部参数透传为 Markdown 块，避免新工具参数丢失。
- `src/tools/worker_tools.py`：`execute_tool_call()` 改为委托 `tool_registry.execute()`。
- `src/cli/chat_command.py`：工具调用展示新增 `WebSearch` / `Fetch`，并对未知工具通用兜底；`/tools` 命令从注册表动态生成。
- `src/ui/static/js/chat.js`：权限卡片与本轮记录对任意工具通用展示。
- `config/workers.yaml`：为 `architect` / `frontend_dev` / `backend_dev` / `tester` 授予 `web_search` / `fetch_url`。

### 流式重试去重

- **问题**：`GatewayClient.chat_stream()` 在流式过程中发生异常时会从头重试，导致已输出的内容被重复发送，用户看到重叠/重复的回答。
- **修复**：只有在**尚未产出任何 chunk** 时才允许重试；一旦开始输出，异常直接报错，不再重试。
- **文件**：`src/gateway/client.py`

### 自动模型故障切换

- **问题**：主模型配额耗尽或连接失败时，请求直接失败，不会自动使用备用模型。
- **实现**：
  - `ModelConfig` 新增 `fallback_models`、`failover_enabled`、`failover_cooldown_seconds`。
  - `providers.yaml` 支持全局 `default_failover_chain`。
  - `GatewayClient.chat()` / `chat_stream()` 递归展开回退链，支持 `A -> B -> C` 并自动去环。
  - 错误分类：认证/请求参数错误直接暴露；模型不可用与 429 才切换；连接错误允许重试后切换。
  - 健康冷却：优先读取 `Retry-After`，也能解析 `5-hour` 等错误时间窗口。
  - 切换时通过 `StreamChunk(type="failover")` / `ChatStreamEvent(type="model_failover")` 通知 CLI 和 Web。
- **CLI 诊断**：`/test-models` 通过 Provider 正式鉴权路径发送最小请求，失败模型立即进入冷却；命令会提示少量 token 消耗。
- **文件**：`src/gateway/client.py`、`src/models/schemas.py`、`config/providers.yaml`、`src/core/agent.py`、`src/cli/chat_command.py`、`src/ui/static/js/chat.js`、`src/ui/static/css/style.css`

### 协作 Worker 稳定性收口

- Worker 支持最多 5 轮工具循环，目录/文件读取结果会回填给模型继续工作。
- 旧配置只要已经授予读取能力，就自动补齐 `list_dir` / `glob_files` / `grep_content` / `read_file`。
- Worker 仅能调用配置授权的工具，Markdown 和原生 `tool_use` 使用同一工具白名单。
- 原生模式不再同时注入 Markdown 工具指令，避免协议冲突。
- Agent / Worker / Reviewer 不再从正文代码块生成 `generated_N` 项目文件。
- 模型只贴代码块时先要求其改用 `write_file`；仍不执行则保留到 `content.txt` 并把任务标记失败，避免伪成功和内容丢失。

## 原则

- 保持项目精简，优先实现最常用、最稳定的工具。
- 不引入不必要的依赖；优先使用标准库或轻量第三方库。
- 新工具必须通过注册表注册，CLI 和 Web 自动可用。
- 外部工具的调用必须遵守当前权限模式（auto/approve/readonly）。

## 预期关键文件

- `src/tools/registry.py` - 工具注册表 ✅
- `src/tools/web_tools.py` - 网页搜索、URL 抓取 ✅
- `src/ui/routers/tools.py` - 工具列表/配置 API（后续）
- `src/ui/static/js/tools.js` - 工具配置前端（后续）
- `src/ui/templates/index.html` - 增加工具配置面板（后续）
- `src/core/agent.py` - 从注册表加载工具说明 ✅
- `src/tools/worker_tools.py` - 通过注册表执行工具 ✅

## 完成标准

- Agent 能通过工具调用完成“搜索 XXX 并总结”类任务。✅
- 新增工具的权限确认与本地工具一致。✅
- `python -m pytest -q` 全绿。✅
- Web UI 能配置/禁用外部工具。（后续迭代）

## 验证

- 单元测试：`tests/test_registry.py`、`tests/test_web_tools.py`（网络全部 mock）、`tests/test_gateway_failover.py`。
- 全量回归：`python -m pytest -q` 通过 `374 passed`。
- CLI：`python run.py chat` 输入“搜索 Claude Code 的最新功能”，Agent 调用 `web_search` 并总结。
- Web：`/chat` 发送“抓取 https://example.com 并总结”，右侧边栏本轮记录显示 `fetch_url`。
- 故障切换：主模型 429/连接失败时，CLI/Web 显示黄色提示并自动切换到备用模型。
- 无付费 mock 演示：`python scripts/demo_failover.py`，输出写入系统临时目录。

## 不在本次范围

- 大规模 MCP 生态集成（先做适配器框架，具体服务器后续按需添加）。
- 浏览器自动化 / 复杂爬虫。
- 打包分发（可执行文件、VS Code 插件等）。

## 下一迭代

Phase 6.6 进入 `docs/Phase6.6-项目结构展示与CLI结果可见性计划.md`：先修复单 Agent 工具循环后最终回答不显示的问题，再实现跨平台 `project_tree`、零 token `/tree` 和 Web 文件树。
