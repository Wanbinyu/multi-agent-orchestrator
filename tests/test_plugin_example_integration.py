"""B6.4 示例插件端到端集成测试。

用真实 ``importlib.metadata.entry_points(group="mao.plugins")`` 发现机制
（临时 dist-info + sys.path）驱动示例插件：发现 -> 启用 -> 加载 -> 执行 ->
关闭。不 pip 安装，wheel 安装验收在 B6.6 ``verify_distribution.py``。
"""
from __future__ import annotations

import importlib
import importlib.metadata
import shutil
import sys
from pathlib import Path

import pytest

from src.plugins.manager import PluginManager
from src.tools.registry import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_PKG_SRC = ROOT / "examples" / "plugins" / "mao_wordcount_plugin" / "mao_wordcount_plugin"


def _write_dist_info(base: Path, name: str, version: str, entry_value: str) -> None:
    dist_info = base / f"{name.replace('-', '_')}-{version}.dist-info"
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n", encoding="utf-8"
    )
    (dist_info / "entry_points.txt").write_text(
        f"[mao.plugins]\nwordcount = {entry_value}\n", encoding="utf-8"
    )


@pytest.fixture
def example_plugin_on_path(tmp_path, monkeypatch):
    """把示例插件包与 dist-info 放到 tmp_path 并加入 sys.path，使其被真实发现。"""
    dest_pkg = tmp_path / "mao_wordcount_plugin"
    shutil.copytree(EXAMPLE_PKG_SRC, dest_pkg)
    _write_dist_info(
        tmp_path,
        name="mao-wordcount-plugin",
        version="0.1.0",
        entry_value="mao_wordcount_plugin:create_plugin",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    # 清理可能残留的模块缓存与元数据缓存
    for mod in list(sys.modules):
        if mod == "mao_wordcount_plugin" or mod.startswith("mao_wordcount_plugin."):
            monkeypatch.delitem(sys.modules, mod, raising=False)
    importlib.invalidate_caches()
    # importlib.metadata 在部分版本有内部缓存
    for cache_attr in ("_distributions", "_entries"):
        cache = getattr(importlib.metadata, cache_attr, None)
        if cache is not None and hasattr(cache, "cache_clear"):
            cache.cache_clear()
    yield tmp_path
    importlib.invalidate_caches()


def _new_manager(registry, config_dir):
    return PluginManager(registry, preset_registry=None, config_dir=str(config_dir))


def test_example_plugin_discovered_via_real_entry_points(example_plugin_on_path):
    eps = importlib.metadata.entry_points(group="mao.plugins")
    values = [ep.value for ep in eps]
    assert "mao_wordcount_plugin:create_plugin" in values


def test_example_plugin_enable_load_execute_shutdown(example_plugin_on_path, tmp_path):
    registry = ToolRegistry()
    mgr = _new_manager(registry, config_dir=tmp_path)

    # 发现
    discovered = mgr.discover()
    assert len(discovered) == 1
    assert discovered[0].manifest.id == "mao-wordcount"
    assert discovered[0].api_compatible is True

    # 默认未启用（load_enabled 幂等，故用 is_enabled 判定默认态）
    assert mgr.is_enabled("mao-wordcount") is False
    assert "word_count" not in registry.list_tools()

    # 启用后加载 -> 工具注册
    mgr.enable("mao-wordcount")
    result = mgr.load_enabled()
    assert result.loaded == 1
    assert "mao-wordcount" in result.loaded_ids
    assert "word_count" in registry.list_tools()

    # 执行工具
    out = registry.execute("word_count", {"text": "hello world"})
    assert out.success is True
    assert "字符数：11" in out.output
    assert "单词数：2" in out.output

    # 关闭 -> 工具注销
    mgr.shutdown()
    assert "word_count" not in registry.list_tools()


def test_example_plugin_list_status(example_plugin_on_path, tmp_path):
    registry = ToolRegistry()
    mgr = _new_manager(registry, config_dir=tmp_path)
    mgr.enable("mao-wordcount")
    statuses = mgr.list_status()
    assert len(statuses) == 1
    s = statuses[0]
    assert s["id"] == "mao-wordcount"
    assert s["enabled"] is True
    assert "tools" in s["capabilities"]
    assert "read_files" in s["permissions"]
    assert s["source"] == "mao-wordcount-plugin"


def test_example_plugin_manifest_declares_v0_api(example_plugin_on_path):
    eps = importlib.metadata.entry_points(group="mao.plugins")
    ep = next(e for e in eps if e.value == "mao_wordcount_plugin:create_plugin")
    plugin = ep.load()()
    assert plugin.manifest.mao_api_version == "0.1"
    assert plugin.manifest.id == "mao-wordcount"
