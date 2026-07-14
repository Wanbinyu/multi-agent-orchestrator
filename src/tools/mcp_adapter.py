"""MCP (Model Context Protocol) 工具源适配器

把外部 MCP server 暴露的工具接入 MAO 的 ToolRegistry，使其与内置工具一样
被 Agent 发现与执行。

MCP 是异步协议，而 MAO 的工具执行是同步的。本模块用一个独立线程承载事件循环
（_AsyncLoopRunner），把异步 MCP 调用桥接为同步方法，可在同步与异步上下文中调用。

依赖：可选安装 `mcp`（pip install mcp）。未安装时给出清晰错误，不影响其他功能。

支持传输：
- stdio：通过子进程 stdin/stdout 通信（command/args/env）
- sse：连接 HTTP/SSE server（url）
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import threading
from typing import Any

from src.tools.registry import ToolSpec
from src.tools.tool_result import ToolResult


class _AsyncLoopRunner:
    """在独立线程运行事件循环，提供同步调用异步协程的桥接"""

    def __init__(self) -> None:
        self.loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self.loop)
        self.loop.run_forever()

    def submit(self, coro) -> concurrent.futures.Future:
        """把协程提交到后台 loop，返回 Future（不阻塞）"""
        return asyncio.run_coroutine_threadsafe(coro, self.loop)

    def run(self, coro, timeout: float = 60.0) -> Any:
        """同步等待协程结果"""
        future = self.submit(coro)
        return future.result(timeout=timeout)

    def shutdown(self) -> None:
        self.loop.call_soon_threadsafe(self.loop.stop)
        self._thread.join(timeout=5)


class MCPToolSource:
    """MCP 工具源：连接一个 MCP server，暴露其工具。"""

    def __init__(self, config: dict[str, Any], name: str = "mcp") -> None:
        self.name = name
        self.config = config
        self._runner: _AsyncLoopRunner | None = None
        self._session: Any = None
        self._stop_event: asyncio.Event | None = None
        self._ready = threading.Event()
        self._init_error: str | None = None
        self._tools_cache: list[ToolSpec] | None = None

        # 校验配置
        if "command" in config:
            self._transport = "stdio"
        elif "url" in config:
            self._transport = "sse"
        else:
            raise ValueError("MCP 配置需提供 command（stdio）或 url（sse）")

    # ---------- 连接生命周期 ----------

    def _ensure_connected(self) -> None:
        if self._session is not None or self._init_error is not None:
            return
        try:
            import mcp  # noqa: F401  type: ignore
        except ImportError:
            self._init_error = "未安装 mcp 包。请运行：pip install mcp"
            return

        self._runner = _AsyncLoopRunner()
        # 后台常驻协程持有连接上下文
        self._runner.submit(self._hold_connection())
        if not self._ready.wait(timeout=30):
            self._init_error = "连接 MCP server 超时"
        # _init_error 可能由 _hold_connection 设置

    async def _hold_connection(self) -> None:
        """常驻协程：建立连接并保持，直到 stop"""
        try:
            if self._transport == "stdio":
                from mcp import StdioServerParameters  # type: ignore
                from mcp.client.stdio import stdio_client  # type: ignore

                params = StdioServerParameters(
                    command=self.config["command"],
                    args=self.config.get("args", []),
                    env=self.config.get("env"),
                )
                transport_ctx = stdio_client(params)
            else:
                from mcp.client.sse import sse_client  # type: ignore

                transport_ctx = sse_client(self.config["url"])

            from mcp import ClientSession  # type: ignore

            self._stop_event = asyncio.Event()
            async with transport_ctx as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    self._session = session
                    self._ready.set()
                    await self._stop_event.wait()
        except Exception as e:
            self._init_error = f"MCP 连接失败：{e}"
            self._ready.set()

    def shutdown(self) -> None:
        """关闭连接与后台 loop"""
        if self._stop_event is not None and self._runner is not None:
            self._runner.loop.call_soon_threadsafe(self._stop_event.set)
        if self._runner is not None:
            self._runner.shutdown()
            self._runner = None
        self._session = None

    # ---------- ToolSource 协议实现 ----------

    def list_tools(self) -> list[ToolSpec]:
        self._ensure_connected()
        if self._init_error is not None:
            return []
        if self._tools_cache is not None:
            return self._tools_cache
        try:
            self._tools_cache = self._runner.run(self._list_tools_async())  # type: ignore[union-attr]
        except Exception as e:
            self._init_error = f"列举 MCP 工具失败：{e}"
            return []
        return self._tools_cache or []

    async def _list_tools_async(self) -> list[ToolSpec]:
        result = await self._session.list_tools()
        specs: list[ToolSpec] = []
        for t in result.tools:
            input_schema = getattr(t, "inputSchema", None) or {"type": "object", "properties": {}}
            params = _schema_to_params(input_schema)
            specs.append(
                ToolSpec(
                    name=getattr(t, "name", ""),
                    description=getattr(t, "description", "") or "",
                    params=params,
                    callable=_noop_callable,
                    category="external",
                )
            )
        return specs

    def execute(self, name: str, params: dict[str, Any]) -> ToolResult:
        self._ensure_connected()
        if self._init_error is not None:
            return ToolResult(success=False, error=self._init_error)
        try:
            return self._runner.run(self._execute_async(name, params))  # type: ignore[union-attr]
        except Exception as e:
            return ToolResult(success=False, error=f"MCP 调用 {name} 失败：{e}")

    async def _execute_async(self, name: str, params: dict[str, Any]) -> ToolResult:
        result = await self._session.call_tool(name, params)
        is_error = getattr(result, "isError", False)
        text_parts: list[str] = []
        for block in getattr(result, "content", []) or []:
            text = getattr(block, "text", None)
            if text:
                text_parts.append(text)
            else:
                text_parts.append(str(block))
        output = "\n".join(text_parts)
        if is_error:
            return ToolResult(success=False, error=output or "MCP 工具返回错误")
        return ToolResult(success=True, output=output)


def _noop_callable(**_: Any) -> ToolResult:
    """MCP 工具的占位 callable（实际执行走 execute()）"""
    return ToolResult(success=False, error="MCP 工具需通过 MCPToolSource.execute 调用")


def _schema_to_params(input_schema: dict[str, Any]) -> dict[str, Any]:
    """把 JSON Schema 的 properties 转为 ToolSpec.params 格式"""
    props = (input_schema or {}).get("properties", {}) or {}
    params: dict[str, Any] = {}
    required = set((input_schema or {}).get("required", []) or [])
    for name, schema in props.items():
        if not isinstance(schema, dict):
            schema = {"type": "string"}
        if name not in required:
            schema = dict(schema)
            schema["default"] = schema.get("default", "")
        params[name] = schema
    return params


# ---------- 配置加载 ----------


def load_mcp_sources_from_config(config_path: str) -> list[MCPToolSource]:
    """从 config/mcp.yaml 加载 MCP server 配置，返回 MCPToolSource 列表。

    配置格式：
        servers:
          - name: filesystem
            command: npx
            args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
          - name: remote
            url: http://localhost:8080/sse
    """
    from pathlib import Path

    import yaml

    path = Path(config_path)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    sources: list[MCPToolSource] = []
    for srv in data.get("servers", []) or []:
        try:
            sources.append(MCPToolSource(srv, name=srv.get("name", "mcp")))
        except Exception:
            continue
    return sources
