"""Worker 工具单元测试"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.tools.worker_tools import (
    discover_project_commands,
    git_status,
    read_file,
    run_command,
    write_file,
)


def test_read_file_success(tmp_path):
    test_file = tmp_path / "hello.txt"
    test_file.write_text("hello world", encoding="utf-8")

    result = read_file("hello.txt", str(tmp_path))
    assert result.success is True
    assert result.output == "hello world"


def test_read_file_not_found(tmp_path):
    result = read_file("not_exist.txt", str(tmp_path))
    assert result.success is False
    assert "不存在" in result.error


def test_read_file_path_traversal(tmp_path):
    result = read_file("../outside.txt", str(tmp_path))
    assert result.success is False
    assert "越界" in result.error


def test_git_status_uses_fixed_readonly_command(tmp_path, monkeypatch):
    completed = MagicMock(returncode=0, stdout="## main\n M README.md\n", stderr="")
    run = MagicMock(return_value=completed)
    monkeypatch.setattr("src.tools.worker_tools.subprocess.run", run)

    result = git_status(".", str(tmp_path))

    assert result.success is True
    assert "## main" in result.output
    run.assert_called_once_with(
        ["git", "status", "--short", "--branch"],
        cwd=str(tmp_path.resolve()),
        capture_output=True,
        text=True,
        timeout=15,
        shell=False,
    )


def test_git_status_rejects_missing_or_non_directory_path(tmp_path):
    file_path = tmp_path / "file.txt"
    file_path.write_text("x", encoding="utf-8")

    assert git_status("missing", str(tmp_path)).success is False
    result = git_status("file.txt", str(tmp_path))
    assert result.success is False
    assert "不是目录" in result.error


def test_run_command_allowed(tmp_path):
    # 使用跨平台的命令
    result = run_command("python --version", str(tmp_path))
    assert result.success is True
    assert "Python" in result.output


def test_run_command_not_allowed(tmp_path):
    result = run_command("rm -rf /", str(tmp_path))
    assert result.success is False
    assert "白名单" in result.error


def test_run_command_custom_whitelist(tmp_path):
    result = run_command("echo hello", str(tmp_path), allowed_prefixes=["echo "])
    assert result.success is True
    assert "hello" in result.output


def test_run_command_timeout(tmp_path):
    # 用 sleep 测试超时，Windows 没有 sleep 命令，用 python 代替
    result = run_command("python -c \"import time; time.sleep(5)\"", str(tmp_path), timeout=1)
    assert result.success is False
    assert "超时" in result.error


def test_run_command_uses_structured_cwd_and_records_trace(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    completed = MagicMock(returncode=0, stdout="built\n", stderr="")
    run = MagicMock(return_value=completed)
    monkeypatch.setattr("src.tools.worker_tools.subprocess.run", run)

    result = run_command("npm run build", str(tmp_path), cwd="project")

    assert result.success is True
    run.assert_called_once_with(
        ["npm", "run", "build"],
        cwd=str(project.resolve()),
        capture_output=True,
        text=True,
        timeout=60,
        shell=False,
    )
    assert result.metadata["cwd"] == str(project.resolve())
    assert result.metadata["argv"] == ["npm", "run", "build"]
    assert result.metadata["exit_code"] == 0
    assert result.metadata["truncated"] is False
    assert result.metadata["duration_ms"] >= 0


def test_run_command_rejects_inline_cd_with_structured_alternative(tmp_path):
    result = run_command(
        "cd G:\\MAO_test && npm run build",
        str(tmp_path),
    )

    assert result.success is False
    assert result.metadata["error_code"] == "inline_cwd"
    assert result.metadata["suggested_params"] == {
        "command": "npm run build",
        "cwd": "G:\\MAO_test",
    }
    assert "cwd" in result.error


@pytest.mark.parametrize(
    "command",
    [
        "npm run build | head",
        "npm test > result.txt",
        "npm run lint && npm test",
    ],
)
def test_run_command_rejects_shell_composition(command, tmp_path):
    result = run_command(command, str(tmp_path))

    assert result.success is False
    assert result.metadata["error_code"] == "shell_syntax"
    assert "单条命令" in result.error


def test_run_command_truncates_output_and_records_original_lengths(tmp_path, monkeypatch):
    completed = MagicMock(returncode=1, stdout="a" * 40, stderr="b" * 30)
    monkeypatch.setattr(
        "src.tools.worker_tools.subprocess.run", MagicMock(return_value=completed)
    )

    result = run_command(
        "python -m pytest -q", str(tmp_path), max_output_chars=32
    )

    assert result.success is False
    assert len(result.output) < 100
    assert "已截断" in result.output
    assert result.metadata["exit_code"] == 1
    assert result.metadata["truncated"] is True
    assert result.metadata["stdout_chars"] == 40
    assert result.metadata["stderr_chars"] == 30


def test_discover_project_commands_reads_package_scripts_without_inventing(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "build": "vite build",
                    "test": "vitest run",
                    "typecheck": "tsc --noEmit",
                },
                "devDependencies": {
                    "vite": "latest",
                    "vitest": "latest",
                    "typescript": "latest",
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "package-lock.json").write_text("{}", encoding="utf-8")

    result = discover_project_commands(".", str(tmp_path))
    payload = json.loads(result.output)

    assert result.success is True
    by_name = {item["name"]: item for item in payload["commands"]}
    assert by_name["build"]["argv"] == ["npm", "run", "build"]
    assert by_name["build"]["supports_temporary_output"] is True
    assert by_name["test"]["argv"] == ["npm", "test"]
    assert by_name["typecheck"]["argv"] == ["npm", "run", "typecheck"]
    assert "lint" not in by_name
    assert payload["recommended_order"] == ["typecheck", "test", "build"]


def test_discover_project_commands_finds_python_verification(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\ntestpaths = ['tests']\n", encoding="utf-8"
    )
    (tmp_path / "tests").mkdir()

    result = discover_project_commands(".", str(tmp_path))
    payload = json.loads(result.output)

    assert result.success is True
    pytest_command = next(item for item in payload["commands"] if item["name"] == "pytest")
    assert pytest_command["argv"] == ["python", "-m", "pytest", "-q"]
    assert pytest_command["cwd"] == str(tmp_path.resolve())


def test_discover_marks_script_with_missing_tool_dependency_unavailable(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"lint": "eslint ."}, "devDependencies": {}}),
        encoding="utf-8",
    )

    result = discover_project_commands(".", str(tmp_path))
    payload = json.loads(result.output)
    lint = payload["commands"][0]

    assert lint["name"] == "lint"
    assert lint["available"] is False
    assert "未声明 eslint" in lint["diagnostic"]
    assert "lint" not in payload["recommended_order"]


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("npm run build", ["npm", "run", "build"]),
        ("npm run lint", ["npm", "run", "lint"]),
        ("npm test", ["npm", "test"]),
        ("python -m pytest -q", ["python", "-m", "pytest", "-q"]),
    ],
)
def test_portable_verification_commands_use_argument_arrays(
    tmp_path, monkeypatch, command, expected
):
    completed = MagicMock(returncode=0, stdout="ok", stderr="")
    run = MagicMock(return_value=completed)
    monkeypatch.setattr("src.tools.worker_tools.subprocess.run", run)

    result = run_command(command, str(tmp_path))

    assert result.success is True
    assert run.call_args.args[0] == expected
    assert run.call_args.kwargs["shell"] is False


def test_vite_build_can_use_cleaned_temporary_output(tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {"build": "vite build"},
                "devDependencies": {"vite": "latest"},
            }
        ),
        encoding="utf-8",
    )
    completed = MagicMock(returncode=0, stdout="built", stderr="")
    run = MagicMock(return_value=completed)
    monkeypatch.setattr("src.tools.worker_tools.subprocess.run", run)

    result = run_command(
        "npm run build",
        str(tmp_path),
        cwd=".",
        temporary_output=True,
    )

    argv = run.call_args.args[0]
    assert argv[:3] == ["npm", "run", "build"]
    assert argv[3:5] == ["--", "--outDir"]
    assert result.success is True
    assert result.metadata["temporary_output"] is True
    assert result.metadata["temporary_output_cleaned"] is True
    assert not Path(result.metadata["temporary_output_path"]).exists()


def test_write_file_relative(tmp_path):
    result = write_file("sub/hello.txt", "hello", str(tmp_path))
    assert result.success is True
    assert (tmp_path / "sub" / "hello.txt").read_text(encoding="utf-8") == "hello"


def test_write_file_absolute_path(tmp_path):
    """用户指定绝对路径时应直接写入该路径，不受 base_dir 限制"""
    target = tmp_path / "external.txt"
    result = write_file(str(target), "abc", str(tmp_path / "output"))
    assert result.success is True
    assert target.read_text(encoding="utf-8") == "abc"
