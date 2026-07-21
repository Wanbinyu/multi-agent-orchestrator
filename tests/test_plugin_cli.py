"""B6.3 mao plugin CLI 与运行时接线测试。"""
from __future__ import annotations

import importlib
import re

import pytest
from typer.testing import CliRunner

import run
from src.plugins.api import (
    CAP_TOOLS,
    MAO_PLUGIN_API_VERSION,
    PERM_READ_FILES,
    PluginManifest,
)
from src.tools.tool_result import ToolResult


runner = CliRunner()

_HELP_ENV = {
    "COLUMNS": "160",
    "TERM": "xterm-256color",
    "NO_COLOR": "1",
}


def _plain(text: str) -> str:
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


# ---------- 模块级测试插件（供 fake entry point 导入）----------


class _CliDemoPlugin:
    def __init__(self):
        self.manifest = PluginManifest(
            id="mao-cli-demo",
            name="CLI Demo",
            version="0.2.0",
            mao_api_version=MAO_PLUGIN_API_VERSION,
            capabilities=[CAP_TOOLS],
            permissions=[PERM_READ_FILES],
            description="a demo plugin",
            homepage="https://example.com/mao-cli-demo",
        )

    def load(self, ctx):
        ctx.register_tool(
            lambda **_: ToolResult(success=True, output="demo"),
            name="cli_demo_tool",
            description="d",
        )

    def shutdown(self):
        pass


def cli_demo_factory():
    return _CliDemoPlugin()


class _FakeEP:
    def __init__(self, name, value, dist_name="mao-cli-demo-pkg"):
        self.name = name
        self.value = value
        self.group = "mao.plugins"
        self._dist_name = dist_name

    @property
    def dist(self):
        dist_name = self._dist_name

        class _D:
            name = dist_name

        return _D()

    def load(self):
        module_path, _, attr = self.value.partition(":")
        return getattr(importlib.import_module(module_path), attr)


def _patch_entry_points(monkeypatch):
    monkeypatch.setattr(
        "src.plugins.manager._default_entry_points",
        lambda: [_FakeEP("cli-demo", "tests.test_plugin_cli:cli_demo_factory")],
    )


# ---------- help ----------


def test_plugin_help_lists_subcommands():
    result = runner.invoke(run.app, ["plugin", "--help"], env=_HELP_ENV)
    assert result.exit_code == 0
    out = _plain(result.output)
    for cmd in ("list", "doctor", "enable", "disable"):
        assert cmd in out


# ---------- 无插件场景 ----------


def test_plugin_list_no_plugins():
    result = runner.invoke(run.app, ["plugin", "list"], env=_HELP_ENV)
    assert result.exit_code == 0
    assert "未发现插件" in _plain(result.output)


def test_plugin_doctor_no_plugins():
    result = runner.invoke(run.app, ["plugin", "doctor"], env=_HELP_ENV)
    assert result.exit_code == 0
    out = _plain(result.output)
    assert "发现 0" in out
    assert "无异常" in out


# ---------- enable/disable 配置往返 ----------


def test_plugin_enable_writes_config(tmp_path):
    config_dir = str(tmp_path)
    result = runner.invoke(
        run.app, ["plugin", "enable", "mao-cli-demo", "--config", config_dir], env=_HELP_ENV
    )
    assert result.exit_code == 0
    config = (tmp_path / "plugins.yaml").read_text(encoding="utf-8")
    assert "mao-cli-demo" in config


def test_plugin_enable_disable_roundtrip(tmp_path):
    config_dir = str(tmp_path)
    runner.invoke(run.app, ["plugin", "enable", "mao-cli-demo", "--config", config_dir], env=_HELP_ENV)
    runner.invoke(run.app, ["plugin", "disable", "mao-cli-demo", "--config", config_dir], env=_HELP_ENV)
    config = (tmp_path / "plugins.yaml").read_text(encoding="utf-8")
    assert "mao-cli-demo" in config
    # disable 写入 disabled 列表
    assert "disabled" in config


# ---------- 有插件场景（fake entry point）----------


def test_plugin_list_shows_discovered_plugin(monkeypatch, tmp_path):
    _patch_entry_points(monkeypatch)
    result = runner.invoke(run.app, ["plugin", "list", "--config", str(tmp_path)], env=_HELP_ENV)
    assert result.exit_code == 0
    out = _plain(result.output)
    assert "mao-cli-demo" in out
    assert "未启用" in out  # 默认未启用


def test_plugin_list_shows_enabled_state(monkeypatch, tmp_path):
    _patch_entry_points(monkeypatch)
    config_dir = str(tmp_path)
    runner.invoke(run.app, ["plugin", "enable", "mao-cli-demo", "--config", config_dir], env=_HELP_ENV)
    result = runner.invoke(run.app, ["plugin", "list", "--config", config_dir], env=_HELP_ENV)
    out = _plain(result.output)
    assert "mao-cli-demo" in out
    assert "已启用" in out
    assert "read_files" in out  # 权限可见


def test_plugin_doctor_loads_enabled_plugin(monkeypatch, tmp_path):
    _patch_entry_points(monkeypatch)
    config_dir = str(tmp_path)
    runner.invoke(run.app, ["plugin", "enable", "mao-cli-demo", "--config", config_dir], env=_HELP_ENV)
    result = runner.invoke(run.app, ["plugin", "doctor", "--config", config_dir], env=_HELP_ENV)
    assert result.exit_code == 0
    out = _plain(result.output)
    assert "发现 1" in out
    assert "加载 1" in out
    assert "mao-cli-demo" in out


def test_plugin_enable_unknown_id_warns(tmp_path):
    config_dir = str(tmp_path)
    result = runner.invoke(
        run.app, ["plugin", "enable", "no-such-plugin", "--config", config_dir], env=_HELP_ENV
    )
    assert result.exit_code == 0
    # 无插件安装时，未发现 -> 提示仍记录启用态
    assert "no-such-plugin" in _plain(result.output)


# ---------- 运行时单例 ----------


def test_runtime_load_and_shutdown_safe(monkeypatch):
    from src.plugins.runtime import load_plugins, shutdown_plugins, get_plugin_status

    # 无插件安装时，加载应为 no-op 且不抛错
    result = load_plugins()
    assert result.discovered == 0
    status = get_plugin_status()
    assert isinstance(status, dict)
    shutdown_plugins()
