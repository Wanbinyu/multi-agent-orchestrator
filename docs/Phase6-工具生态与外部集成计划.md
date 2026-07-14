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
| 代码执行沙箱 | ⏳ 计划中 |
| MCP 适配器 | ⏳ 计划中 |
| UI 工具配置面板 | ⏳ 计划中 |

## Goal

扩展 Agent 的工具能力，建立统一的工具注册与管理机制，并接入外部高频工具：

1. **统一工具注册表**：`src/tools/registry.py` ✅
2. **内置高频工具**：
   - 网页搜索（DuckDuckGo，可选 `duckduckgo-search` 增强）✅
   - URL 抓取（获取网页内容并转换为 Markdown）✅
3. **可选增强**（后续迭代）：
   - 代码执行沙箱
   - MCP 适配器，接入外部工具服务器
   - IDE 插件 / VS Code 扩展
4. **UI 配置**（后续迭代）：在连接配置页增加外部工具 API Key / MCP 服务器设置。

## 已实现

### 统一工具注册表

`src/tools/registry.py` 提供 `ToolRegistry` 单例：

- 装饰器 `@tool_registry.register(name, description, params, category)` 注册工具。
- `build_instructions(tool_names=None)` 自动生成系统提示中的工具说明（Markdown 代码块示例）。
- `execute(name, params, base_dir, allowed_prefixes)` 统一执行，自动注入 `base_dir` / `allowed_prefixes`，异常兜底为 `ToolResult(success=False)`。
- 工具按 `category` 分类：`read` / `write` / `execute` / `external` / `unsafe`。

内置工具在 `src/tools/worker_tools.py` 导入时自动注册：`read_file`、`write_file`、`run_command`、`search_project_files`、`search_memory`、`web_search`、`fetch_url`。

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

- 单元测试：`tests/test_registry.py`、`tests/test_web_tools.py`（网络全部 mock）。
- 全量回归：`python -m pytest -q` 通过 `237 passed`。
- CLI：`python run.py chat` 输入“搜索 Claude Code 的最新功能”，Agent 调用 `web_search` 并总结。
- Web：`/chat` 发送“抓取 https://example.com 并总结”，右侧边栏本轮记录显示 `fetch_url`。

## 不在本次范围

- 大规模 MCP 生态集成（先做适配器框架，具体服务器后续按需添加）。
- 浏览器自动化 / 复杂爬虫。
- 打包分发（可执行文件、VS Code 插件等）。
