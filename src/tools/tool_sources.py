"""外部工具源（ToolSource）扩展点

为 MCP（Model Context Protocol）等外部工具服务器预留接入位置。
MCP 的实际实现在 src/tools/mcp_adapter.py（MCPToolSource）。

接入方式：
    from src.tools.registry import tool_registry
    from src.tools.mcp_adapter import MCPToolSource, load_mcp_sources_from_config

    # 单个 server
    source = MCPToolSource({"command": "npx", "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]})
    tool_registry.add_source(source)

    # 或从配置文件批量加载
    for src in load_mcp_sources_from_config("config/mcp.yaml"):
        tool_registry.add_source(src)

注册后，MCP server 暴露的工具会自动出现在 Agent 的工具说明中，
并通过 tool_registry.execute() 统一执行（与内置工具一致，并受 Hooks 拦截）。
"""
from __future__ import annotations

from src.tools.mcp_adapter import MCPToolSource, load_mcp_sources_from_config

__all__ = ["MCPToolSource", "load_mcp_sources_from_config"]
