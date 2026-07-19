"""Worker 执行器单元测试"""
from pathlib import Path
from unittest.mock import MagicMock

from src.core.worker import (
    Worker,
    _expand_legacy_read_tools,
    build_tool_instructions,
    process_tool_calls,
)
from src.models.schemas import ChatResponse, FrontendBuildContract, Task


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
    assert results[0]["permission"]["action"] == "allow"
    assert results[0]["metadata"]["cwd"] == str(tmp_path.resolve())


def test_process_tool_calls_limits_invalid_command_corrections(tmp_path):
    state = {"preflight_failures": 0}
    invalid = '```tool:run_command\n{"command": "cd bad && npm test"}\n```'

    _processed, first = process_tool_calls(
        invalid, str(tmp_path), command_state=state
    )
    _processed, second = process_tool_calls(
        invalid, str(tmp_path), command_state=state
    )
    _processed, third = process_tool_calls(
        invalid, str(tmp_path), command_state=state
    )

    assert first[0]["metadata"]["error_code"] == "inline_cwd"
    assert second[0]["metadata"]["error_code"] == "inline_cwd"
    assert third[0]["metadata"]["error_code"] == "correction_limit"
    assert state["preflight_failures"] == 2


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


def test_integration_worker_cannot_replace_command_evidence_with_prose(tmp_path):
    project = tmp_path / "project"
    (project / "src" / "pages").mkdir(parents=True)
    (project / "src" / "main.tsx").write_text(
        'import "./pages/Home";\n', encoding="utf-8"
    )
    (project / "src" / "pages" / "Home.tsx").write_text(
        "export default function Home() {}\n", encoding="utf-8"
    )
    (project / "package.json").write_text(
        '{"dependencies":{"react":"latest"}}', encoding="utf-8"
    )
    contract = FrontendBuildContract(
        project_root=str(project),
        entrypoints=["src/main.tsx"],
        routes=[{"path": "/", "target": "src/pages/Home.tsx"}],
        dependencies=["react"],
        ownership={"integration": []},
        verification_commands=["npm run build"],
        smoke_paths=["/"],
        smoke={
            "start_command": [
                "python", "-m", "http.server", "{port}", "--bind", "127.0.0.1"
            ],
            "routes": [
                {"path": "/", "assertions": [{"selector": "body"}]}
            ],
        },
    )
    task = Task(
        id="integration", type="tester", title="集成验证", input="验证项目",
        assigned_model="glm-ark", execution_mode="verify",
        frontend_stage="integration", frontend_contract=contract,
    )
    gateway = MagicMock()
    gateway.resolve_model.return_value = "glm-ark"
    gateway.chat.return_value = ChatResponse(
        content="我已经运行 npm run build，一切正常。",
        model="glm-ark", provider="ark",
    )
    worker = Worker(
        gateway,
        {"tester": {"tools": ["read_file", "run_command"]}},
    )

    result = worker.execute(task, output_dir=str(tmp_path / "output"))

    assert result.success is False
    assert "缺少真实成功命令证据：npm run build" in result.error
