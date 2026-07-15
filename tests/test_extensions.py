"""扩展加载器测试"""
from __future__ import annotations

from src.tools import extensions
from src.tools.registry import tool_registry


def test_load_extensions_no_config(tmp_path, monkeypatch):
    """无配置文件时静默返回 0"""
    extensions.reset_load_flag()
    # 清理可能的全局 hooks
    tool_registry.hooks.clear()
    stats = extensions.load_extensions(str(tmp_path))
    assert stats == {"hooks": 0, "mcp_sources": 0}


def test_load_extensions_is_idempotent(tmp_path):
    extensions.reset_load_flag()
    s1 = extensions.load_extensions(str(tmp_path))
    s2 = extensions.load_extensions(str(tmp_path))
    # 第二次因幂等标志直接返回 0
    assert s2 == {"hooks": 0, "mcp_sources": 0}
    assert s1 == s2


def test_load_extensions_loads_hooks(tmp_path):
    """有 hooks.yaml 时加载钩子到全局 registry"""
    extensions.reset_load_flag()
    tool_registry.hooks.clear()
    cfg = tmp_path / "hooks.yaml"
    cfg.write_text(
        "pre:\n  - tests.test_hooks._sample_pre\n", encoding="utf-8"
    )
    stats = extensions.load_extensions(str(tmp_path))
    assert stats["hooks"] == 1
    assert len(tool_registry.hooks._pre) == 1
    # 清理
    tool_registry.hooks.clear()


def test_load_extensions_mcp_missing_package(tmp_path):
    """有 mcp.yaml 但 mcp 未安装时，源被加入但 list_tools 返回空"""
    extensions.reset_load_flag()
    # 先清理已注册的 sources（无法直接清理，用新 registry 验证逻辑）
    cfg = tmp_path / "mcp.yaml"
    cfg.write_text(
        "servers:\n  - name: fs\n    command: npx\n    args: ['-y', 'srv']\n",
        encoding="utf-8",
    )
    stats = extensions.load_extensions(str(tmp_path))
    # 源被加入（即使 mcp 未安装，构造时不连接）
    assert stats["mcp_sources"] == 1


def test_shutdown_extensions_closes_and_removes_sources():
    from unittest.mock import MagicMock

    source = MagicMock()
    source.list_tools.return_value = []
    tool_registry.add_source(source)
    extensions.shutdown_extensions()
    source.shutdown.assert_called_once()
    assert tool_registry._sources == []
