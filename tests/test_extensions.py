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
    assert stats == {"hooks": 0, "mcp_sources": 0, "diagnostics": []}


def test_load_extensions_is_idempotent(tmp_path):
    extensions.reset_load_flag()
    s1 = extensions.load_extensions(str(tmp_path))
    s2 = extensions.load_extensions(str(tmp_path))
    # 第二次返回第一次的防御性副本，便于多个入口读取同一诊断。
    assert s2 == {"hooks": 0, "mcp_sources": 0, "diagnostics": []}
    assert s1 == s2
    assert s1 is not s2


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


def test_invalid_hook_is_diagnosed_without_blocking_valid_hook(tmp_path):
    extensions.reset_load_flag()
    tool_registry.hooks.clear()
    (tmp_path / "hooks.yaml").write_text(
        "pre:\n"
        "  - missing.module.SECRET_KEY_123\n"
        "  - tests.test_hooks._sample_pre\n",
        encoding="utf-8",
    )

    stats = extensions.load_extensions(str(tmp_path))

    assert stats["hooks"] == 1
    assert len(stats["diagnostics"]) == 1
    assert stats["diagnostics"][0]["code"] == "hook_import_error"
    assert "SECRET_KEY_123" not in str(stats)


def test_extension_diagnostics_are_globally_bounded_and_redacted(tmp_path):
    extensions.reset_load_flag()
    tool_registry.hooks.clear()
    invalid_hooks = "\n".join(
        f"  - missing.module.secret_{index}" for index in range(20)
    )
    (tmp_path / "hooks.yaml").write_text(
        f"pre:\n{invalid_hooks}\n", encoding="utf-8"
    )
    (tmp_path / "mcp.yaml").write_text(
        "servers:\n"
        "  - name: invalid\n"
        "    env:\n"
        "      API_KEY: SUPER_SECRET_VALUE\n",
        encoding="utf-8",
    )

    stats = extensions.load_extensions(str(tmp_path))

    serialized = str(stats)
    assert len(stats["diagnostics"]) == 10
    assert "secret_" not in serialized
    assert "SUPER_SECRET_VALUE" not in serialized
    assert str(tmp_path) not in serialized


def test_malformed_extension_config_does_not_block_core_startup(tmp_path):
    extensions.reset_load_flag()
    (tmp_path / "hooks.yaml").write_text("pre: [unterminated", encoding="utf-8")
    (tmp_path / "mcp.yaml").write_text("servers: [unterminated", encoding="utf-8")

    stats = extensions.load_extensions(str(tmp_path))

    assert stats["hooks"] == 0
    assert stats["mcp_sources"] == 0
    assert {item["code"] for item in stats["diagnostics"]} == {
        "hook_config_error",
        "mcp_config_error",
    }
