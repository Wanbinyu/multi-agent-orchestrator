"""CLI 入口单元测试"""
from __future__ import annotations

import os
import re
from unittest.mock import ANY, MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

import run
from src.models.schemas import ChatResponse, ReviewResult, Task, TaskPlan, TaskResult


runner = CliRunner()

# CI runners report a narrow TTY and Rich injects ANSI spans that can split
# option tokens in the raw help buffer. Force a wide plain-friendly width.
_HELP_ENV = {
    **os.environ,
    "COLUMNS": "160",
    "TERM": "xterm-256color",
    "NO_COLOR": "1",
}


def _plain(text: str) -> str:
    """Strip ANSI SGR sequences so help assertions are terminal-independent."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def test_version_option():
    result = runner.invoke(run.app, ["--version"], env=_HELP_ENV)
    assert result.exit_code == 0
    assert f"MAO {run.__version__}" in _plain(result.output)


def test_run_help_shows_all_options():
    result = runner.invoke(run.app, ["run", "--help"], env=_HELP_ENV)
    out = _plain(result.output)
    assert result.exit_code == 0
    assert "--output" in out
    assert "-o" in out
    assert "--config" in out
    assert "-c" in out
    assert "--max-workers" in out
    assert "-w" in out
    assert "--orchestrator-model" in out
    assert "-m" in out
    assert "--yes" in out
    assert "-y" in out


def test_setup_help_shows_config_option():
    result = runner.invoke(run.app, ["setup", "--help"], env=_HELP_ENV)
    out = _plain(result.output)
    assert result.exit_code == 0
    assert "--config" in out
    assert "-c" in out


def test_agent_setup_help_shows_config_option():
    result = runner.invoke(run.app, ["agent-setup", "--help"], env=_HELP_ENV)
    out = _plain(result.output)
    assert result.exit_code == 0
    assert "--config" in out
    assert "-c" in out


def test_web_help_shows_server_options():
    result = runner.invoke(run.app, ["web", "--help"], env=_HELP_ENV)
    out = _plain(result.output)
    assert result.exit_code == 0
    assert "--host" in out
    assert "--port" in out
    assert "--no-open" in out


def test_no_args_launches_default_cli(monkeypatch):
    launched = MagicMock()
    monkeypatch.setattr(run, "_run_default_cli", launched)

    result = runner.invoke(run.app, [], env=_HELP_ENV)

    assert result.exit_code == 0, result.output
    launched.assert_called_once_with()


def test_agent_setup_reloads_newly_written_environment(monkeypatch):
    wizard = MagicMock()
    wizard_factory = MagicMock(return_value=wizard)
    reload_env = MagicMock()
    monkeypatch.setattr(run, "AgentSetupWizard", wizard_factory)
    monkeypatch.setattr(run, "load_dotenv", reload_env)

    run._run_agent_setup("workspace-config")

    wizard_factory.assert_called_once_with(
        config_path="workspace-config/providers.yaml"
    )
    wizard.run.assert_called_once_with()
    reload_env.assert_called_once_with(override=True)


def test_default_cli_starts_chat_in_current_workspace(tmp_path, monkeypatch):
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "providers.yaml").write_text("providers: {}\nmodels: {}\n", encoding="utf-8")
    launch_chat = MagicMock()
    monkeypatch.setattr(run, "_run_chat", launch_chat)

    run._run_default_cli(str(config_dir))

    launch_chat.assert_called_once_with(config_dir=str(config_dir))


def test_default_cli_non_tty_clean_directory_exits_with_guidance(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run.sys.stdin, "isatty", lambda: False)

    with pytest.raises(typer.Exit) as exc_info:
        run._run_default_cli()

    assert exc_info.value.exit_code == 2
    assert list(tmp_path.iterdir()) == []


def test_default_cli_requires_console_output_for_first_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(run.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(run.sys.stdout, "isatty", lambda: False)

    with pytest.raises(typer.Exit) as exc_info:
        run._run_default_cli()

    assert exc_info.value.exit_code == 2
    assert list(tmp_path.iterdir()) == []


def test_web_command_uses_shared_server(monkeypatch):
    from src.ui import cli as ui_cli

    serve = MagicMock()
    monkeypatch.setattr(ui_cli, "serve", serve)

    result = runner.invoke(
        run.app,
        ["web", "--host", "0.0.0.0", "--port", "9000", "--no-open"],
        env=_HELP_ENV,
    )

    assert result.exit_code == 0, result.output
    serve.assert_called_once_with(host="0.0.0.0", port=9000, open_browser=False)


def test_maybe_insert_run_subcommand_with_bare_request():
    assert run._maybe_insert_run_subcommand(["run.py", "开发登录页面"]) == ["run.py", "run", "开发登录页面"]


def test_maybe_insert_run_subcommand_keeps_setup():
    assert run._maybe_insert_run_subcommand(["run.py", "setup"]) == ["run.py", "setup"]


def test_maybe_insert_run_subcommand_keeps_agent_setup():
    assert run._maybe_insert_run_subcommand(["run.py", "agent-setup"]) == ["run.py", "agent-setup"]


def test_maybe_insert_run_subcommand_keeps_web():
    assert run._maybe_insert_run_subcommand(["run.py", "web"]) == ["run.py", "web"]


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
    mock_orchestrator.plan.assert_called_once_with("开发一个登录页面", memory_context=ANY)
    mock_dispatcher.dispatch.assert_called_once_with(plan, output_dir=str(output_dir), memory_context=ANY)
    mock_reviewer.review.assert_called_once()


def test_run_command_without_request_argument_fails():
    result = runner.invoke(run.app, ["run"])
    assert result.exit_code != 0
    assert "Missing argument" in result.output or "REQUEST" in result.output


def test_run_command_rejects_unknown_option():
    result = runner.invoke(run.app, ["run", "hello", "--unknown-option"])
    assert result.exit_code != 0
    assert "Error" in result.output
