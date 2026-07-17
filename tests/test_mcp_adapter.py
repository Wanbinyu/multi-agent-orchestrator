"""MCP 适配器测试（mock mcp 包，不依赖真实安装）"""
from __future__ import annotations

import asyncio
import sys
import types
from unittest.mock import MagicMock

import pytest

from src.tools.mcp_adapter import MCPToolSource, _AsyncLoopRunner, _schema_to_params


# ---------- _AsyncLoopRunner ----------


def test_async_loop_runner_runs_coro_sync():
    runner = _AsyncLoopRunner()

    async def coro():
        await asyncio.sleep(0.01)
        return 42

    assert runner.run(coro()) == 42
    runner.shutdown()


def test_async_loop_runner_propagates_exception():
    runner = _AsyncLoopRunner()

    async def coro():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        runner.run(coro())
    runner.shutdown()


# ---------- _schema_to_params ----------


def test_schema_to_params_required_and_optional():
    schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "p"},
            "limit": {"type": "integer"},
        },
        "required": ["path"],
    }
    params = _schema_to_params(schema)
    assert "path" in params
    assert "limit" in params
    # 非必填参数应被加上 default
    assert "default" in params["limit"]
    # 必填参数不加 default
    assert "default" not in params["path"]


def test_schema_to_params_empty():
    assert _schema_to_params({}) == {}
    assert _schema_to_params({"type": "object"}) == {}


# ---------- MCPToolSource 配置校验 ----------


def test_mcp_requires_command_or_url():
    with pytest.raises(ValueError):
        MCPToolSource({})


def test_mcp_stdio_config_constructs():
    src = MCPToolSource({"command": "npx", "args": ["-y", "srv"], "env": {"X": "1"}})
    assert src._transport == "stdio"


def test_mcp_sse_config_constructs():
    src = MCPToolSource({"url": "http://localhost:8080/sse"})
    assert src._transport == "sse"


# ---------- 未安装 mcp 时的优雅降级 ----------


def test_list_tools_returns_empty_when_mcp_missing():
    src = MCPToolSource({"command": "npx", "args": ["srv"]})
    # mcp 未安装（测试环境）
    tools = src.list_tools()
    assert tools == []
    assert src._init_error is not None
    assert "mcp" in src._init_error


def test_execute_returns_error_when_mcp_missing():
    src = MCPToolSource({"command": "npx", "args": ["srv"]})
    result = src.execute("any_tool", {"x": 1})
    assert result.success is False
    assert "mcp" in result.error


# ---------- 用 mock mcp 测试连接与调用 ----------


def _install_mock_mcp(monkeypatch, tools=None, call_text=None, call_is_error=False):
    """注入一个假的 mcp 包到 sys.modules。

    tools: list[dict] 每个 dict 含 name/description/input_schema
    """
    tools = tools or []

    class _Tool:
        def __init__(self, name, description, input_schema):
            self.name = name
            self.description = description
            self.inputSchema = input_schema

    class _ListResult:
        def __init__(self, tools):
            self.tools = tools

    class _Content:
        def __init__(self, text):
            self.text = text

    class _CallResult:
        def __init__(self, content, is_error=False):
            self.content = content
            self.isError = is_error

    built_tools = [
        _Tool(t.get("name", ""), t.get("description", ""), t.get("input_schema", {}))
        for t in tools
    ]
    call_result = None
    if call_text is not None:
        call_result = _CallResult([_Content(call_text)], is_error=call_is_error)

    class _Session:
        def __init__(self, read, write):
            self._read = read
            self._write = write

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def initialize(self):
            return None

        async def list_tools(self):
            return _ListResult(built_tools)

        async def call_tool(self, name, params):
            return call_result

    class _StdioParams:
        def __init__(self, command, args, env=None):
            self.command = command
            self.args = args
            self.env = env

    class _StdioCtx:
        async def __aenter__(self):
            return (MagicMock(), MagicMock())

        async def __aexit__(self, *a):
            return False

    class _SSECtx:
        async def __aenter__(self):
            return (MagicMock(), MagicMock())

        async def __aexit__(self, *a):
            return False

    def _stdio_client(params):
        return _StdioCtx()

    def _sse_client(url):
        return _SSECtx()

    mcp_mod = types.ModuleType("mcp")
    mcp_mod.ClientSession = _Session
    mcp_mod.StdioServerParameters = _StdioParams
    monkeypatch.setitem(sys.modules, "mcp", mcp_mod)

    stdio_mod = types.ModuleType("mcp.client.stdio")
    stdio_mod.stdio_client = _stdio_client
    sse_mod = types.ModuleType("mcp.client.sse")
    sse_mod.sse_client = _sse_client
    client_mod = types.ModuleType("mcp.client")
    monkeypatch.setitem(sys.modules, "mcp.client", client_mod)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", stdio_mod)
    monkeypatch.setitem(sys.modules, "mcp.client.sse", sse_mod)


def test_list_tools_with_mock_mcp(monkeypatch):
    _install_mock_mcp(
        monkeypatch,
        tools=[
            {"name": "fs_read", "description": "read a file",
             "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
        ],
    )
    src = MCPToolSource({"command": "npx", "args": ["srv"]})
    try:
        tools = src.list_tools()
        assert len(tools) == 1
        assert tools[0].name == "fs_read"
        assert tools[0].category == "external"
        assert "path" in tools[0].params
    finally:
        src.shutdown()


def test_execute_with_mock_mcp(monkeypatch):
    _install_mock_mcp(monkeypatch, call_text="hello world", call_is_error=False)
    src = MCPToolSource({"command": "npx", "args": ["srv"]})
    try:
        result = src.execute("fs_read", {"path": "/tmp/x"})
        assert result.success is True
        assert result.output == "hello world"
    finally:
        src.shutdown()


def test_execute_handles_mcp_error(monkeypatch):
    _install_mock_mcp(monkeypatch, call_text="file not found", call_is_error=True)
    src = MCPToolSource({"command": "npx", "args": ["srv"]})
    try:
        result = src.execute("fs_read", {"path": "/nope"})
        assert result.success is False
        assert "file not found" in result.error
    finally:
        src.shutdown()


def test_execute_redacts_runtime_exception_text():
    def fail_safely(coro):
        coro.close()
        raise RuntimeError("API_KEY=SUPER_SECRET_VALUE")

    src = MCPToolSource({"command": "npx", "args": ["srv"]})
    src._session = MagicMock()
    src._runner = MagicMock()
    src._runner.run.side_effect = fail_safely

    result = src.execute("secret_tool_name", {})

    assert result.success is False
    assert "RuntimeError" in result.error
    assert "SUPER_SECRET_VALUE" not in result.error
    assert "secret_tool_name" not in result.error


# ---------- 配置加载 ----------


def test_load_mcp_sources_from_config_missing(tmp_path):
    from src.tools.mcp_adapter import load_mcp_sources_from_config

    assert load_mcp_sources_from_config(str(tmp_path / "nope.yaml")) == []


def test_load_mcp_sources_from_config(tmp_path):
    from src.tools.mcp_adapter import load_mcp_sources_from_config

    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n"
        "  - name: fs\n"
        "    command: npx\n"
        "    args: ['-y', 'srv']\n"
        "  - name: remote\n"
        "    url: http://localhost:8080/sse\n"
        "  - name: bad\n"  # 缺 command/url，应跳过
        "    foo: bar\n",
        encoding="utf-8",
    )
    sources = load_mcp_sources_from_config(str(cfg))
    assert len(sources) == 2
    assert sources[0]._transport == "stdio"
    assert sources[1]._transport == "sse"


def test_detailed_mcp_loader_reports_bad_entry_and_keeps_valid_source(tmp_path):
    from src.tools.mcp_adapter import load_mcp_sources_from_config_detailed

    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n"
        "  - name: bad\n"
        "    env:\n"
        "      API_KEY: SUPER_SECRET_VALUE\n"
        "  - name: valid\n"
        "    command: npx\n",
        encoding="utf-8",
    )

    sources, diagnostics = load_mcp_sources_from_config_detailed(str(cfg))

    assert len(sources) == 1
    assert len(diagnostics) == 1
    assert diagnostics[0]["entry"] == "servers[0]"
    assert "SUPER_SECRET_VALUE" not in str(diagnostics)
    assert str(tmp_path) not in str(diagnostics)
