"""ToolSource 扩展点测试"""
from __future__ import annotations

from src.tools.registry import ToolRegistry, ToolSpec
from src.tools.tool_result import ToolResult


class _FakeSource:
    """模拟一个外部工具源"""

    def __init__(self, tools: list[ToolSpec], results: dict[str, ToolResult] | None = None):
        self._tools = tools
        self._results = results or {}

    def list_tools(self) -> list[ToolSpec]:
        return self._tools

    def execute(self, name: str, params: dict) -> ToolResult:
        return self._results.get(
            name, ToolResult(success=True, output=f"executed {name}")
        )


def _spec(name: str) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=f"外部工具 {name}",
        params={"input": {"type": "string"}},
        callable=lambda **_: ToolResult(success=True, output=""),
        category="external",
    )


def test_add_source_makes_tools_discoverable():
    reg = ToolRegistry()
    reg.add_source(_FakeSource([_spec("ext_tool_1"), _spec("ext_tool_2")]))
    names = reg.list_tools()
    assert "ext_tool_1" in names
    assert "ext_tool_2" in names


def test_get_finds_source_tool():
    reg = ToolRegistry()
    reg.add_source(_FakeSource([_spec("ext_tool")]))
    spec = reg.get("ext_tool")
    assert spec is not None
    assert spec.name == "ext_tool"


def test_local_tool_takes_priority_over_source():
    reg = ToolRegistry()

    @reg.register(
        name="shared",
        description="本地版本",
        params={},
        category="read",
    )
    def shared(base_dir: str = ".") -> ToolResult:
        return ToolResult(success=True, output="local")

    reg.add_source(_FakeSource([_spec("shared")]))
    # get 返回本地版本
    spec = reg.get("shared")
    assert spec.description == "本地版本"
    # execute 也走本地
    result = reg.execute("shared", {}, base_dir=".")
    assert result.output == "local"


def test_execute_dispatches_to_source():
    reg = ToolRegistry()
    source = _FakeSource(
        [_spec("ext_tool")],
        results={"ext_tool": ToolResult(success=True, output="from source")},
    )
    reg.add_source(source)
    result = reg.execute("ext_tool", {"input": "x"}, base_dir=".")
    assert result.success is True
    assert result.output == "from source"


def test_execute_unknown_tool_not_in_source():
    reg = ToolRegistry()
    reg.add_source(_FakeSource([]))
    result = reg.execute("nope", {}, base_dir=".")
    assert result.success is False
    assert "未知工具" in result.error


def test_build_instructions_includes_source_tools():
    reg = ToolRegistry()
    reg.add_source(_FakeSource([_spec("ext_tool")]))
    instructions = reg.build_instructions()
    assert "ext_tool" in instructions
    assert "```tool:ext_tool" in instructions


def test_build_instructions_subset_includes_source_via_get():
    reg = ToolRegistry()
    reg.add_source(_FakeSource([_spec("ext_tool")]))
    instructions = reg.build_instructions(["ext_tool"])
    assert "ext_tool" in instructions


def test_mcp_tool_source_validates_config():
    from src.tools.mcp_adapter import MCPToolSource

    # 缺 command 和 url 应报错
    import pytest

    with pytest.raises(ValueError):
        MCPToolSource({})

    # stdio 配置可构造（不连接）
    src = MCPToolSource({"command": "npx", "args": ["-y", "server"]})
    assert src._transport == "stdio"

    # sse 配置可构造
    src2 = MCPToolSource({"url": "http://localhost:8080/sse"})
    assert src2._transport == "sse"


def test_mcp_tool_source_graceful_without_mcp_package():
    from src.tools.mcp_adapter import MCPToolSource

    src = MCPToolSource({"command": "npx", "args": ["-y", "server"]})
    # mcp 未安装时，list_tools 返回空且记录错误
    tools = src.list_tools()
    assert tools == []
    assert src._init_error is not None
    assert "mcp" in src._init_error
