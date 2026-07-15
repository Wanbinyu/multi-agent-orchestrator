"""CLI 权限模式切换相关单元测试"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.document import Document

from src.cli.chat_command import (
    COMMANDS,
    SlashCommandCompleter,
    _cmd_test_models,
    _cmd_tree,
    _format_tool_action,
    _parse_tree_args,
    _print_welcome,
    _set_mode,
    _summarize_tool_activity,
)
from src.core.session import Session


def _make_session(mode: str = "approve") -> Session:
    return Session(
        id="test-session",
        title="test",
        created_at="2026-07-12T00:00:00+00:00",
        updated_at="2026-07-12T00:00:00+00:00",
        output_dir="output",
        approval_mode=mode,  # type: ignore[arg-type]
    )


def test_set_mode_valid():
    session = _make_session("approve")
    agent = MagicMock()
    agent.approval_mode = "approve"
    mode_ref = ["approve"]

    assert _set_mode(session, agent, mode_ref, "auto") is True
    assert session.approval_mode == "auto"
    assert agent.approval_mode == "auto"
    assert mode_ref[0] == "auto"


def test_set_mode_invalid():
    session = _make_session("approve")
    agent = MagicMock()
    agent.approval_mode = "approve"
    mode_ref = ["approve"]

    assert _set_mode(session, agent, mode_ref, "invalid") is False
    assert session.approval_mode == "approve"
    assert mode_ref[0] == "approve"


def test_set_mode_cycle_logic():
    """验证 /mode 无参数时的循环顺序 approve -> readonly -> auto -> approve"""
    from src.cli.chat_command import MODES

    session = _make_session("approve")
    agent = MagicMock()
    agent.approval_mode = "approve"
    mode_ref = ["approve"]

    for expected in ["readonly", "auto", "approve"]:
        idx = MODES.index(mode_ref[0])
        next_mode = MODES[(idx + 1) % len(MODES)]
        _set_mode(session, agent, mode_ref, next_mode)
        assert mode_ref[0] == expected


def test_cmd_test_models_checks_every_model_and_warns_about_cost(capsys):
    gateway = MagicMock()
    gateway.models = {"main": MagicMock(), "fallback": MagicMock()}
    gateway.test_model.side_effect = [
        {"success": True, "response_time_ms": 12.0, "error": ""},
        {"success": False, "response_time_ms": 4.0, "error": "429 quota"},
    ]

    _cmd_test_models(gateway)

    assert [call.args[0] for call in gateway.test_model.call_args_list] == [
        "main", "fallback",
    ]
    output = capsys.readouterr().out
    assert "少量 token" in output
    assert "健康冷却" in output


def _complete(text: str):
    completer = SlashCommandCompleter()
    return list(completer.get_completions(Document(text), CompleteEvent()))


def test_slash_command_completion_opens_on_slash():
    names = {item.text for item in _complete("/")}
    assert "/new" in names
    assert "/memory search" in names
    assert "/tools" in names
    assert "/tree" in names
    assert "/exit" in names


def test_slash_command_completion_filters_as_user_types():
    names = {item.text for item in _complete("/memory s")}
    assert names == {"/memory search", "/memory summarize"}

    names = {item.text for item in _complete("/tes")}
    assert names == {"/test-models"}


def test_slash_command_completion_ignores_normal_text_and_arguments():
    assert _complete("检查项目") == []
    assert _complete("/new 项目会话") == []


def test_help_remains_available_but_welcome_is_compact(capsys):
    assert "/memory add" in COMMANDS
    assert "输入 / 可打开命令列表" in COMMANDS

    _print_welcome("session-1", "approve")
    output = capsys.readouterr().out
    assert "输入 / 查看命令" in output
    assert "/memory add" not in output


def test_tool_action_and_summary_are_human_readable_and_compact():
    assert _format_tool_action("read_file", {"path": "G:/demo/README.md"}) == (
        "读取文件 G:/demo/README.md"
    )
    calls = [
        {"tool": "list_dir", "params": {"path": "G:/demo"}, "success": True},
        {"tool": "read_file", "params": {"path": "G:/demo/a.py"}, "success": True},
        {"tool": "read_file", "params": {"path": "G:/demo/a.py"}, "success": True},
        {
            "tool": "write_file",
            "params": {"path": "G:/demo/plan.md", "content": "one\ntwo"},
            "success": False,
            "error": "只读模式",
        },
    ]

    summary = "\n".join(_summarize_tool_activity(calls))

    assert "浏览 1 个目录" in summary
    assert "读取 1 个文件" in summary
    assert "1 次重复操作" in summary
    assert "2 次成功，1 次失败" not in summary
    assert "3 次成功，1 次失败" in summary
    assert "只读模式" in summary


def test_tree_args_preserve_windows_paths_with_spaces():
    assert _parse_tree_args(r"G:\MAO test 5") == (r"G:\MAO test", 5)
    assert _parse_tree_args(r"G:\MAO test") == (r"G:\MAO test", 4)
    assert _parse_tree_args("") == (".", 4)


def test_cmd_tree_is_local_and_reports_errors(tmp_path, capsys):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print(1)")

    assert _cmd_tree(f"{tmp_path} 2") is True
    output = capsys.readouterr().out
    assert "main.py" in output
    assert "未调用模型" in output

    assert _cmd_tree(str(tmp_path / "missing")) is False
    assert "项目树生成失败" in capsys.readouterr().out
