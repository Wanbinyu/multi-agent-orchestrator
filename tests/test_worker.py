"""Worker 执行器单元测试"""
from pathlib import Path

from src.core.worker import build_tool_instructions, process_tool_calls


def test_build_tool_instructions_with_read_and_run():
    instructions = build_tool_instructions(["write_file", "read_file", "run_command"])
    assert "read_file" in instructions
    assert "run_command" in instructions
    assert "tool:read_file" in instructions
    assert "tool:run_command" in instructions


def test_build_tool_instructions_only_write_file():
    instructions = build_tool_instructions(["write_file"])
    assert instructions == ""


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
