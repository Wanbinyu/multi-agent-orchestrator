"""CLI 入口单元测试"""
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

import run
from src.models.schemas import ChatResponse, ReviewResult, Task, TaskPlan, TaskResult


runner = CliRunner()


def test_run_help_shows_all_options():
    result = runner.invoke(run.app, ["run", "--help"])
    assert result.exit_code == 0
    assert "--output" in result.output
    assert "-o" in result.output
    assert "--config" in result.output
    assert "-c" in result.output
    assert "--max-workers" in result.output
    assert "-w" in result.output
    assert "--orchestrator-model" in result.output
    assert "-m" in result.output


def test_setup_help_shows_config_option():
    result = runner.invoke(run.app, ["setup", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.output
    assert "-c" in result.output


def test_agent_setup_help_shows_config_option():
    result = runner.invoke(run.app, ["agent-setup", "--help"])
    assert result.exit_code == 0
    assert "--config" in result.output
    assert "-c" in result.output


def test_maybe_insert_run_subcommand_with_bare_request():
    assert run._maybe_insert_run_subcommand(["run.py", "开发登录页面"]) == ["run.py", "run", "开发登录页面"]


def test_maybe_insert_run_subcommand_keeps_setup():
    assert run._maybe_insert_run_subcommand(["run.py", "setup"]) == ["run.py", "setup"]


def test_maybe_insert_run_subcommand_keeps_agent_setup():
    assert run._maybe_insert_run_subcommand(["run.py", "agent-setup"]) == ["run.py", "agent-setup"]


def test_maybe_insert_run_subcommand_keeps_help():
    assert run._maybe_insert_run_subcommand(["run.py", "--help"]) == ["run.py", "--help"]
    assert run._maybe_insert_run_subcommand(["run.py", "-h"]) == ["run.py", "-h"]


def test_maybe_insert_run_subcommand_no_args():
    assert run._maybe_insert_run_subcommand(["run.py"]) == ["run.py"]


def test_run_command_executes_full_flow(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    output_dir = tmp_path / "out"

    # 最小配置
    (config_dir / "providers.yaml").write_text("providers:\nmodels:\n", encoding="utf-8")
    (config_dir / "workers.yaml").write_text("orchestrator:\n  model: glm-ark\n", encoding="utf-8")

    task = Task(id="t1", type="frontend", title="登录页面", input="写登录页面", assigned_model="glm-ark")
    plan = TaskPlan(summary="写登录页面", tasks=[task])
    result = TaskResult(
        task=task,
        success=True,
        content="```html\n<input>\n```",
        response=ChatResponse(
            content="```html\n<input>\n```",
            model="glm-ark",
            provider="ark",
            input_tokens=10,
            output_tokens=5,
            cost_usd=0.0,
        ),
        files_written=[str(output_dir / "frontend_t1" / "generated_1.html")],
    )

    mock_gateway = MagicMock()
    mock_orchestrator = MagicMock()
    mock_orchestrator.plan.return_value = plan
    mock_worker = MagicMock()
    mock_dispatcher = MagicMock()
    mock_dispatcher.dispatch.return_value = [result]
    mock_reviewer = MagicMock()
    mock_reviewer.review.return_value = ReviewResult(passed=True, issues=[], final_output="完成")

    monkeypatch.setattr(run, "GatewayClient", lambda **kwargs: mock_gateway)
    monkeypatch.setattr(run, "Orchestrator", lambda *args, **kwargs: mock_orchestrator)
    monkeypatch.setattr(run, "Worker", lambda *args, **kwargs: mock_worker)
    monkeypatch.setattr(run, "Dispatcher", lambda *args, **kwargs: mock_dispatcher)
    monkeypatch.setattr(run, "Reviewer", lambda *args, **kwargs: mock_reviewer)

    result_invoke = runner.invoke(
        run.app,
        [
            "run",
            "开发一个登录页面",
            "--output", str(output_dir),
            "--config", str(config_dir),
            "--max-workers", "1",
        ],
    )

    assert result_invoke.exit_code == 0, result_invoke.output
    assert "开始处理需求" in result_invoke.output
    assert "审查通过" in result_invoke.output
    mock_orchestrator.plan.assert_called_once_with("开发一个登录页面")
    mock_dispatcher.dispatch.assert_called_once_with(plan, output_dir=str(output_dir))
    mock_reviewer.review.assert_called_once()


def test_run_command_without_request_argument_fails():
    result = runner.invoke(run.app, ["run"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "REQUEST" in result.output


def test_run_command_rejects_unknown_option():
    result = runner.invoke(run.app, ["run", "hello", "--unknown-option"])
    assert result.exit_code != 0
    assert "Error" in result.output
