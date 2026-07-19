"""ToolRegistry 单元测试"""
from __future__ import annotations

from src.tools.registry import ToolRegistry, tool_registry
from src.tools.tool_result import ToolResult


def _make_registry() -> ToolRegistry:
    reg = ToolRegistry()

    @reg.register(
        name="echo",
        description="返回输入文本",
        params={"text": {"type": "string", "description": "文本"}},
        category="read",
    )
    def echo(text: str, base_dir: str = ".") -> ToolResult:
        return ToolResult(success=True, output=text)

    def add(a: int, b: int) -> ToolResult:
        return ToolResult(success=True, output=str(a + b))

    reg.register_function(
        add,
        name="add",
        description="两数相加",
        params={
            "a": {"type": "integer"},
            "b": {"type": "integer"},
        },
        category="read",
    )
    return reg


def test_register_and_get():
    reg = _make_registry()
    assert reg.get("echo") is not None
    assert reg.get("add") is not None
    assert reg.get("missing") is None


def test_list_tools():
    reg = _make_registry()
    names = reg.list_tools()
    assert "echo" in names
    assert "add" in names


def test_execute_basic():
    reg = _make_registry()
    result = reg.execute("echo", {"text": "hello"}, base_dir=".")
    assert result.success is True
    assert result.output == "hello"


def test_execute_injects_base_dir():
    reg = _make_registry()

    @reg.register(
        name="where",
        description="返回 base_dir",
        params={},
        category="read",
    )
    def where(base_dir: str = ".") -> ToolResult:
        return ToolResult(success=True, output=base_dir)

    result = reg.execute("where", {}, base_dir="/tmp/project")
    assert result.success is True
    assert result.output == "/tmp/project"


def test_execute_unknown_tool():
    reg = _make_registry()
    result = reg.execute("nope", {}, base_dir=".")
    assert result.success is False
    assert "未知工具" in result.error


def test_build_instructions_all():
    reg = _make_registry()
    instructions = reg.build_instructions()
    assert "echo" in instructions
    assert "add" in instructions
    assert "```tool:echo" in instructions
    assert "```tool:add" in instructions


def test_build_instructions_subset():
    reg = _make_registry()
    instructions = reg.build_instructions(["echo"])
    assert "echo" in instructions
    assert "add" not in instructions


def test_build_instructions_empty():
    reg = ToolRegistry()
    assert reg.build_instructions() == ""


def test_build_instructions_example_values():
    reg = _make_registry()
    instructions = reg.build_instructions(["echo"])
    assert "text" in instructions


def test_execute_handles_exception():
    reg = ToolRegistry()

    @reg.register(
        name="boom",
        description="总是抛错",
        params={},
        category="read",
    )
    def boom() -> ToolResult:
        raise ValueError("炸了")

    result = reg.execute("boom", {}, base_dir=".")
    assert result.success is False
    assert "炸了" in result.error


def test_global_registry_has_builtins():
    # 触发内置工具注册
    import src.tools.worker_tools  # noqa: F401
    import src.tools.web_tools  # noqa: F401

    names = tool_registry.list_tools()
    for expected in (
        "read_file",
        "write_file",
        "run_command",
        "discover_project_commands",
        "frontend_smoke",
        "search_project_files",
        "search_memory",
        "web_search",
        "fetch_url",
    ):
        assert expected in names, f"缺少内置工具：{expected}"


def test_run_command_schema_exposes_structured_cwd_and_temp_output():
    import src.tools.worker_tools  # noqa: F401

    schema = tool_registry.build_tool_schemas("anthropic", ["run_command"])[0]
    properties = schema["input_schema"]["properties"]

    assert properties["cwd"]["type"] == "string"
    assert properties["temporary_output"]["type"] == "boolean"
    assert "cwd" not in schema["input_schema"]["required"]
    spec = tool_registry.get("run_command")
    assert spec is not None
    assert spec.params["cwd"]["default"] == "."
    assert spec.params["temporary_output"]["default"] is False


def test_frontend_smoke_schema_is_structured_execute_tool():
    import src.tools.worker_tools  # noqa: F401

    spec = tool_registry.get("frontend_smoke")
    assert spec is not None
    assert spec.category == "execute"
    schema = tool_registry.build_tool_schemas("anthropic", ["frontend_smoke"])[0]
    properties = schema["input_schema"]["properties"]
    assert properties["contract"]["type"] == "object"
    assert "artifact_dir" not in schema["input_schema"]["required"]
    assert spec.params["artifact_dir"]["default"] == "smoke-artifacts"
