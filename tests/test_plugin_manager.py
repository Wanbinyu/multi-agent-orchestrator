"""B6.2 插件管理器单元测试。"""
from __future__ import annotations

import importlib

import pytest

from src.plugins.api import (
    CAP_TOOLS,
    CAP_TOOL_SOURCE,
    MAO_PLUGIN_API_VERSION,
    PERM_READ_FILES,
    PluginManifest,
)
from src.plugins.manager import PluginManager
from src.tools.registry import ToolRegistry
from src.tools.tool_result import ToolResult


# ---------- 测试用插件与工厂（模块级，供 fake entry point 导入）----------


class _GoodPlugin:
    def __init__(self):
        self.manifest = PluginManifest(
            id="mao-good",
            name="Good",
            version="0.1.0",
            mao_api_version=MAO_PLUGIN_API_VERSION,
            capabilities=[CAP_TOOLS],
            permissions=[PERM_READ_FILES],
        )

    def load(self, ctx):
        ctx.register_tool(
            lambda **_: ToolResult(success=True, output="ok"),
            name="good_tool",
            description="a good tool",
        )

    def shutdown(self):
        pass


def good_factory():
    return _GoodPlugin()


class _FailingPlugin:
    def __init__(self):
        self.manifest = PluginManifest(
            id="mao-fail",
            name="Fail",
            version="0.1.0",
            mao_api_version=MAO_PLUGIN_API_VERSION,
            capabilities=[CAP_TOOLS],
        )

    def load(self, ctx):
        # 先注册一个工具，再抛错：验证回滚清掉半加载状态
        ctx.register_tool(
            lambda **_: ToolResult(success=True), name="fail_tool", description="d"
        )
        raise RuntimeError("boom")

    def shutdown(self):
        pass


def failing_factory():
    return _FailingPlugin()


class _IncompatPlugin:
    def __init__(self):
        self.manifest = PluginManifest(
            id="mao-incompat",
            name="Incompat",
            version="0.1.0",
            mao_api_version="0.2",  # 不兼容
            capabilities=[CAP_TOOLS],
        )

    def load(self, ctx):
        ctx.register_tool(
            lambda **_: ToolResult(success=True), name="never_tool", description="d"
        )

    def shutdown(self):
        pass


def incompat_factory():
    return _IncompatPlugin()


class _SourcePlugin:
    def __init__(self):
        self.manifest = PluginManifest(
            id="mao-source",
            name="Source",
            version="0.1.0",
            mao_api_version=MAO_PLUGIN_API_VERSION,
            capabilities=[CAP_TOOL_SOURCE],
        )
        self.source = _StubSource()

    def load(self, ctx):
        ctx.add_tool_source(self.source)

    def shutdown(self):
        pass


def source_factory():
    return _SourcePlugin()


class _StubSource:
    def __init__(self):
        self.shutdown_called = 0

    def list_tools(self):
        return []

    def execute(self, name, params):  # pragma: no cover - 不会被调用
        return ToolResult(success=False, error="no tools")

    def shutdown(self):
        self.shutdown_called += 1


# ---------- fake entry point ----------


class _FakeEP:
    """模拟 importlib.metadata.EntryPoint 的最小接口。"""

    def __init__(self, name, value, dist_name=""):
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
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)


def _manager(registry, tmp_path, eps):
    return PluginManager(
        tool_registry=registry,
        preset_registry=None,
        config_dir=str(tmp_path),
        entry_points_finder=lambda: eps,
    )


# ---------- 发现 ----------


def test_discover_finds_compatible_plugin(registry, tmp_path):
    eps = [_FakeEP("good", "tests.test_plugin_manager:good_factory", dist_name="mao-good-pkg")]
    mgr = _manager(registry, tmp_path, eps)
    discovered = mgr.discover()
    assert len(discovered) == 1
    assert discovered[0].manifest.id == "mao-good"
    assert discovered[0].api_compatible is True
    assert discovered[0].dist_name == "mao-good-pkg"


def test_discover_marks_incompatible(registry, tmp_path):
    eps = [_FakeEP("incompat", "tests.test_plugin_manager:incompat_factory")]
    mgr = _manager(registry, tmp_path, eps)
    discovered = mgr.discover()
    assert discovered[0].api_compatible is False


def test_discover_dedups_same_id(registry, tmp_path):
    eps = [
        _FakeEP("good1", "tests.test_plugin_manager:good_factory"),
        _FakeEP("good2", "tests.test_plugin_manager:good_factory"),
    ]
    mgr = _manager(registry, tmp_path, eps)
    discovered = mgr.discover()
    assert len(discovered) == 1  # 同 id 去重


def test_discover_bad_entry_point_isolated(registry, tmp_path):
    eps = [_FakeEP("bad", "tests.test_plugin_manager:does_not_exist")]
    mgr = _manager(registry, tmp_path, eps)
    discovered = mgr.discover()
    assert discovered == []
    assert any(d["code"] == "plugin_discover_error" for d in mgr.last_result().diagnostics)


# ---------- 启用门控 ----------


def test_load_skips_disabled_by_default(registry, tmp_path):
    eps = [_FakeEP("good", "tests.test_plugin_manager:good_factory")]
    mgr = _manager(registry, tmp_path, eps)
    result = mgr.load_enabled()
    assert result.discovered == 1
    assert result.loaded == 0
    assert result.skipped_disabled == 1
    assert "good_tool" not in registry.list_tools()


def test_load_enabled_plugin_registers_tool(registry, tmp_path):
    eps = [_FakeEP("good", "tests.test_plugin_manager:good_factory")]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-good")
    result = mgr.load_enabled()
    assert result.loaded == 1
    assert "mao-good" in result.loaded_ids
    assert "good_tool" in registry.list_tools()


def test_incompatible_plugin_rejected_not_loaded(registry, tmp_path):
    eps = [_FakeEP("incompat", "tests.test_plugin_manager:incompat_factory")]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-incompat")
    result = mgr.load_enabled()
    assert result.rejected_incompatible == 1
    assert result.loaded == 0
    assert any(d["code"] == "plugin_api_incompatible" for d in result.diagnostics)
    assert "never_tool" not in registry.list_tools()


# ---------- 隔离 ----------


def test_failing_plugin_does_not_block_others(registry, tmp_path):
    eps = [
        _FakeEP("fail", "tests.test_plugin_manager:failing_factory"),
        _FakeEP("good", "tests.test_plugin_manager:good_factory"),
    ]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-fail")
    mgr.enable("mao-good")
    result = mgr.load_enabled()
    assert result.failed == 1
    assert result.loaded == 1
    assert "good_tool" in registry.list_tools()
    # 失败插件的半加载工具被回滚
    assert "fail_tool" not in registry.list_tools()
    assert any(d["code"] == "plugin_load_error" for d in result.diagnostics)


def test_no_plugins_no_behavior_change(registry, tmp_path):
    mgr = _manager(registry, tmp_path, [])
    result = mgr.load_enabled()
    assert result.discovered == 0
    assert result.loaded == 0
    assert result.diagnostics == []


# ---------- 幂等与关闭 ----------


def test_load_is_idempotent(registry, tmp_path):
    eps = [_FakeEP("good", "tests.test_plugin_manager:good_factory")]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-good")
    first = mgr.load_enabled()
    second = mgr.load_enabled()
    assert first.loaded_ids == second.loaded_ids
    assert registry.list_tools().count("good_tool") == 1


def test_shutdown_unregisters_contributions(registry, tmp_path):
    eps = [_FakeEP("good", "tests.test_plugin_manager:good_factory")]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-good")
    mgr.load_enabled()
    assert "good_tool" in registry.list_tools()
    mgr.shutdown()
    assert "good_tool" not in registry.list_tools()


def test_shutdown_shuts_down_tool_sources(registry, tmp_path):
    eps = [_FakeEP("source", "tests.test_plugin_manager:source_factory")]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-source")
    mgr.load_enabled()
    plugin = mgr.loaded_plugins()["mao-source"]
    mgr.shutdown()
    assert plugin.source.shutdown_called >= 1


# ---------- 启用态配置 ----------


def test_enable_disable_roundtrip(registry, tmp_path):
    eps = [_FakeEP("good", "tests.test_plugin_manager:good_factory")]
    mgr = _manager(registry, tmp_path, eps)
    assert mgr.is_enabled("mao-good") is False
    mgr.enable("mao-good")
    assert mgr.is_enabled("mao-good") is True
    mgr.disable("mao-good")
    assert mgr.is_enabled("mao-good") is False


def test_disable_overrides_enable(registry, tmp_path):
    eps = [_FakeEP("good", "tests.test_plugin_manager:good_factory")]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-good")
    mgr.disable("mao-good")
    result = mgr.load_enabled()
    assert result.loaded == 0
    assert result.skipped_disabled == 1


# ---------- 状态展示 ----------


def test_list_status_reflects_discovery_and_enable(registry, tmp_path):
    eps = [
        _FakeEP("good", "tests.test_plugin_manager:good_factory"),
        _FakeEP("incompat", "tests.test_plugin_manager:incompat_factory"),
    ]
    mgr = _manager(registry, tmp_path, eps)
    mgr.enable("mao-good")
    statuses = mgr.list_status()
    by_id = {s["id"]: s for s in statuses}
    assert by_id["mao-good"]["enabled"] is True
    assert by_id["mao-good"]["api_compatible"] is True
    assert by_id["mao-good"]["permissions"] == [PERM_READ_FILES]
    assert by_id["mao-incompat"]["api_compatible"] is False
    assert by_id["mao-incompat"]["enabled"] is False


# ---------- fixtures ----------


@pytest.fixture
def registry():
    return ToolRegistry()
