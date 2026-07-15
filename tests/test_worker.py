"""Worker 执行器单元测试"""
from pathlib import Path

from src.core.worker import (
    _expand_legacy_read_tools,
    build_tool_instructions,
    process_tool_calls,
)
from src.models.schemas import Task


def test_build_tool_instructions_with_read_and_run():
    instructions = build_tool_instructions(["write_file", "read_file", "run_command", "search_project_files", "search_memory"])
    assert "read_file" in instructions
    assert "run_command" in instructions
    assert "search_project_files" in instructions
    assert "search_memory" in instructions
    assert "tool:read_file" in instructions
    assert "tool:search_project_files" in instructions


def test_build_tool_instructions_only_write_file():
    instructions = build_tool_instructions(["write_file"])
    assert "write_file" in instructions
    assert "tool:write_file" in instructions
    assert "search_project_files" not in instructions


def test_legacy_read_permission_enables_directory_tools():
    tools = _expand_legacy_read_tools(["write_file", "search_project_files"])
    for name in ("read_file", "list_dir", "glob_files", "grep_content"):
        assert name in tools


def test_process_tool_calls_read_file(tmp_path):
    test_file = tmp_path / "data.txt"
    test_file.write_text("file content", encoding="utf-8")

    content = 'Some text\n```tool:read_file\n{"path": "data.txt"}\n```\nMore text'
    processed, results = process_tool_calls(content, str(tmp_path))

    assert len(results) == 1
    assert results[0]["tool"] == "read_file"
    assert results[0]["success"] is True
    assert results[0]["output"] == "file content"
    assert "file content" in processed
    assert "```tool:read_file" not in processed


def test_process_tool_calls_run_command(tmp_path):
    content = '```tool:run_command\n{"command": "python --version"}\n```'
    processed, results = process_tool_calls(content, str(tmp_path))

    assert len(results) == 1
    assert results[0]["tool"] == "run_command"
    assert results[0]["success"] is True
    assert "Python" in results[0]["output"]
    assert "Python" in processed


def test_process_tool_calls_invalid_json(tmp_path):
    content = '```tool:read_file\n{invalid json}\n```'
    processed, results = process_tool_calls(content, str(tmp_path))

    assert len(results) == 1
    assert results[0]["success"] is False
    assert "解析失败" in processed


def test_process_tool_calls_unknown_tool(tmp_path):
    content = '```tool:unknown_tool\n{"x": 1}\n```'
    processed, results = process_tool_calls(content, str(tmp_path))

    assert len(results) == 1
    assert results[0]["tool"] == "unknown_tool"
    assert results[0]["success"] is False
    assert "未知工具" in results[0]["error"]


def test_process_tool_calls_rejects_ungranted_tool(tmp_path):
    content = '```tool:run_command\n{"command": "python --version"}\n```'
    processed, results = process_tool_calls(
        content, str(tmp_path), allowed_tools=["read_file"]
    )

    assert results[0]["success"] is False
    assert "未获授权" in results[0]["error"]
    assert "被拒绝" in processed


def test_readonly_task_rejects_write_even_when_worker_config_grants_it(tmp_path):
    task = Task(
        id="read", type="analyst", title="只读", input="检查",
        assigned_model="glm-ark", execution_mode="read",
    )
    content = '```tool:write_file\n{"path":"bad.txt","content":"bad"}\n```'

    processed, results = process_tool_calls(
        content,
        str(tmp_path),
        allowed_tools=["write_file"],
        task=task,
    )

    assert results[0]["success"] is False
    assert "只读子任务禁止" in results[0]["error"]
    assert "被拒绝" in processed
    assert not (tmp_path / "bad.txt").exists()


def test_worker_rejects_absolute_write_outside_owned_paths(tmp_path):
    owned = tmp_path / "owned"
    outside = tmp_path / "outside.txt"
    task = Task(
        id="write", type="backend_dev", title="写入", input="实现",
        assigned_model="glm-ark", owned_paths=[str(owned)],
    )

    _processed, denied = process_tool_calls(
        f'```tool:write_file\n{{"path":{outside.as_posix()!r},"content":"bad"}}\n```'.replace("'", '"'),
        str(tmp_path / "isolated"),
        allowed_tools=["write_file"],
        task=task,
    )
    allowed_path = owned / "ok.txt"
    _processed, allowed = process_tool_calls(
        f'```tool:write_file\n{{"path":{allowed_path.as_posix()!r},"content":"ok"}}\n```'.replace("'", '"'),
        str(tmp_path / "isolated"),
        allowed_tools=["write_file"],
        task=task,
    )

    assert denied[0]["success"] is False
    assert "不属于子任务" in denied[0]["error"]
    assert allowed[0]["success"] is True
    assert allowed_path.read_text(encoding="utf-8") == "ok"


def test_process_tool_calls_reuses_reads_and_invalidates_after_write(tmp_path):
    target = tmp_path / "data.txt"
    target.write_text("old", encoding="utf-8")
    cache = {}
    content = (
        '```tool:read_file\n{"path":"data.txt"}\n```\n'
        '```tool:read_file\n{"path":"data.txt"}\n```\n'
        '```tool:write_file\n{"path":"data.txt","content":"new"}\n```\n'
        '```tool:read_file\n{"path":"data.txt"}\n```'
    )

    _processed, results = process_tool_calls(
        content,
        str(tmp_path),
        allowed_tools=["read_file", "write_file"],
        read_cache=cache,
    )

    assert [result.get("cached", False) for result in results] == [
        False, True, False, False,
    ]
    assert results[-1]["output"] == "new"


def test_process_tool_calls_supports_special_closing_token(tmp_path):
    (tmp_path / "data.txt").write_text("ok", encoding="utf-8")
    content = (
        '```tool:read_file\n{"path":"data.txt"}'
        '<|tool_calls_section_end|>'
    )
    processed, results = process_tool_calls(content, str(tmp_path))

    assert results[0]["success"] is True
    assert "ok" in processed
