"""B6.1 Plugin API v0 契约单元测试。"""
from __future__ import annotations

import pytest

from src.plugins.api import (
    CAP_HOOKS,
    CAP_PROVIDER_PRESET,
    CAP_TOOLS,
    CAP_TOOL_SOURCE,
    KNOWN_CAPABILITIES,
    KNOWN_PERMISSIONS,
    MAO_PLUGIN_API_VERSION,
    PERM_READ_FILES,
    PERM_WRITE_FILES,
    SUPPORTED_API_VERSIONS,
    PluginContext,
    PluginManifest,
    is_supported_api_version,
)
from src.tools.registry import ToolRegistry
from src.tools.tool_result import ToolResult


def _manifest(**overrides):
    base = dict(
        id="mao-demo",
        name="Demo",
        version="0.1.0",
        mao_api_version=MAO_PLUGIN_API_VERSION,
        capabilities=[CAP_TOOLS],
        permissions=[PERM_READ_FILES],
    )
    base.update(overrides)
    return PluginManifest(**base)


# ---------- manifest 校验 ----------


def test_manifest_valid_minimal():
    m = _manifest()
    assert m.id == "mao-demo"
    assert m.mao_api_version == "0.1"
    assert m.capabilities == [CAP_TOOLS]


@pytest.mark.parametrize("bad_id", ["MAO-Demo", "1demo", "demo_x", "", " demo"])
def test_manifest_rejects_bad_id(bad_id):
    with pytest.raises(ValueError):
        _manifest(id=bad_id)


@pytest.mark.parametrize("field_name", ["name", "version", "mao_api_version"])
def test_manifest_rejects_empty_required(field_name):
    with pytest.raises(ValueError):
        _manifest(**{field_name: "  "})


def test_manifest_rejects_unknown_capability():
    with pytest.raises(ValueError):
        _manifest(capabilities=[CAP_TOOLS, "teleport"])


def test_manifest_rejects_unknown_permission():
    with pytest.raises(ValueError):
        _manifest(permissions=[PERM_READ_FILES, "root"])


def test_manifest_accepts_all_known_capabilities_and_permissions():
    m = _manifest(
        capabilities=list(KNOWN_CAPABILITIES),
        permissions=list(KNOWN_PERMISSIONS),
    )
    assert set(m.capabilities) == KNOWN_CAPABILITIES
    assert set(m.permissions) == KNOWN_PERMISSIONS


# ---------- API 版本兼容 ----------


def test_supported_api_version_contains_v0():
    assert MAO_PLUGIN_API_VERSION == "0.1"
    assert SUPPORTED_API_VERSIONS == frozenset({"0.1"})


def test_is_supported_api_version():
    assert is_supported_api_version("0.1") is True
    assert is_supported_api_version("0.2") is False
    assert is_supported_api_version("") is False
    assert is_supported_api_version("1.0") is False


# ---------- PluginContext 注册与回滚 ----------


class _StubPresetRegistry:
    def __init__(self):
        self.presets: dict[str, dict] = {}

    def register_preset(self, key, preset):
        self.presets[key] = preset

    def unregister_preset(self, key):
        self.presets.pop(key, None)


class _StubToolSource:
    def __init__(self, name="stub-tool"):
        self._name = name
        self.shutdown_called = 0

    def list_tools(self):
        from src.tools.registry import ToolSpec

        return [ToolSpec(name=self._name, description="stub", params={}, callable=lambda **_: ToolResult(success=True))]

    def execute(self, name, params):
        return ToolResult(success=True, output="stub")

    def shutdown(self):
        self.shutdown_called += 1


def _ctx(preset_registry=None):
    registry = ToolRegistry()
    return registry, PluginContext(registry, preset_registry=preset_registry)


def test_context_register_tool_and_rollback():
    registry, ctx = _ctx()

    def my_tool(text: str = "") -> ToolResult:
        return ToolResult(success=True, output=text)

    ctx.register_tool(my_tool, name="my_tool", description="d", params={"text": {"type": "string"}})
    assert "my_tool" in registry.list_tools()
    assert ctx.contributed_summary()["tools"] == 1

    ctx.rollback()
    assert "my_tool" not in registry.list_tools()
    assert ctx.contributed_summary()["tools"] == 0


def test_context_add_tool_source_rolls_back_and_shuts_down():
    registry, ctx = _ctx()
    source = _StubToolSource(name="stub-tool")
    ctx.add_tool_source(source)
    assert "stub-tool" in registry.list_tools()

    ctx.rollback()
    assert "stub-tool" not in registry.list_tools()
    assert source.shutdown_called == 1


def test_context_hooks_and_rollback():
    registry, ctx = _ctx()
    calls = {"pre": 0, "post": 0}

    def pre(name, params):
        calls["pre"] += 1
        return None

    def post(name, params, result):
        calls["post"] += 1
        return None

    ctx.add_pre_hook(pre)
    ctx.add_post_hook(post)
    assert registry.hooks._pre == [pre]  # noqa: SLF001
    assert registry.hooks._post == [post]  # noqa: SLF001

    ctx.rollback()
    assert registry.hooks._pre == []  # noqa: SLF001
    assert registry.hooks._post == []  # noqa: SLF001


def test_context_provider_preset_and_rollback():
    presets = _StubPresetRegistry()
    _registry, ctx = _ctx(preset_registry=presets)
    ctx.register_provider_preset("my-provider", {"name": "My", "type": "openai", "base_url": "x", "env_var": "Y"})
    assert "my-provider" in presets.presets

    ctx.rollback()
    assert "my-provider" not in presets.presets


def test_context_provider_preset_without_registry_raises():
    _registry, ctx = _ctx(preset_registry=None)
    with pytest.raises(RuntimeError):
        ctx.register_provider_preset("k", {})


def test_context_model_capabilities_recorded():
    _registry, ctx = _ctx()
    ctx.register_model_capabilities("my-model", {"capabilities": ["coding"]})
    assert ctx.model_capabilities == {"my-model": {"capabilities": ["coding"]}}
    assert ctx.contributed_summary()["model_capabilities"] == 1

    ctx.rollback()
    assert ctx.model_capabilities == {}


def test_context_contributed_summary_after_mixed_registrations():
    _registry, ctx = _ctx()
    ctx.register_tool(lambda **_: ToolResult(success=True), name="t", description="d")
    ctx.add_tool_source(_StubToolSource())
    ctx.add_pre_hook(lambda n, p: None)
    ctx.register_model_capabilities("m", {})

    summary = ctx.contributed_summary()
    assert summary == {
        "tools": 1,
        "tool_sources": 1,
        "pre_hooks": 1,
        "post_hooks": 0,
        "presets": 0,
        "model_capabilities": 1,
    }


def test_context_idempotent_rollback():
    _registry, ctx = _ctx()
    ctx.register_tool(lambda **_: ToolResult(success=True), name="t", description="d")
    ctx.rollback()
    ctx.rollback()  # 第二次回滚不应抛错
    assert ctx.contributed_summary()["tools"] == 0


# ---------- 集成：回滚后工具源 shutdown 仍被调用 ----------


def test_rollback_leaves_pre_existing_tools_intact():
    registry, ctx = _ctx()

    def existing(text: str = "") -> ToolResult:
        return ToolResult(success=True)

    registry.register_function(existing, name="existing", description="d")
    ctx.register_tool(lambda **_: ToolResult(success=True), name="plugin_tool", description="d")
    assert set(registry.list_tools()) >= {"existing", "plugin_tool"}

    ctx.rollback()
    assert "existing" in registry.list_tools()
    assert "plugin_tool" not in registry.list_tools()
