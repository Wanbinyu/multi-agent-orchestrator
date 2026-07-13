# Phase 6：工具生态与外部集成

## Context

Phase 5（长期记忆与项目上下文）已 100% 完成。下一步将进入 **Phase 6：工具生态与外部集成**，让 Agent 不再局限于本地文件与命令，能够访问外部信息、调用网页服务、接入更多工具。

## Goal

扩展 Agent 的工具能力，建立统一的工具注册与管理机制，并接入外部高频工具：

1. **统一工具注册表**：`src/tools/registry.py`
2. **内置高频工具**：
   - 网页搜索（如 DuckDuckGo / Bing / Google）
   - URL 抓取（获取网页内容并转换为 Markdown）
3. **可选增强**：
   - 代码执行沙箱
   - MCP 适配器，接入外部工具服务器
   - IDE 插件 / VS Code 扩展
4. **UI 配置**：在连接配置页增加外部工具 API Key / MCP 服务器设置。

## 原则

- 保持项目精简，优先实现最常用、最稳定的工具。
- 不引入不必要的依赖；优先使用标准库或轻量第三方库。
- 新工具必须通过注册表注册，CLI 和 Web 自动可用。
- 外部工具的调用必须遵守当前权限模式（auto/approve/readonly）。

## 预期关键文件

- `src/tools/registry.py` — 工具注册表
- `src/tools/web_tools.py` — 网页搜索、URL 抓取
- `src/ui/routers/tools.py` — 工具列表/配置 API
- `src/ui/static/js/tools.js` — 工具配置前端
- `src/ui/templates/index.html` — 增加工具配置面板
- `src/core/agent.py` — 从注册表加载工具说明
- `src/tools/worker_tools.py` — 通过注册表执行工具

## 完成标准

- Agent 能通过工具调用完成“搜索 XXX 并总结”类任务。
- 新增工具的权限确认与本地工具一致。
- `python -m pytest -q` 全绿。
- Web UI 能配置/禁用外部工具。

## 不在本次范围

- 大规模 MCP 生态集成（先做适配器框架，具体服务器后续按需添加）。
- 浏览器自动化 / 复杂爬虫。
- 打包分发（可执行文件、VS Code 插件等）。
