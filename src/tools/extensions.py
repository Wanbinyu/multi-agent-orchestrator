"""启动时加载扩展（Hooks + MCP 工具源）

从 config/ 目录读取 hooks.yaml 与 mcp.yaml，注册到全局 tool_registry。
配置缺失时静默跳过，不影响主流程。
"""
from __future__ import annotations

from pathlib import Path

from src.tools.registry import tool_registry

_loaded = False


def load_extensions(config_dir: str = "config") -> dict[str, int]:
    """加载 hooks 与 MCP 配置到全局 tool_registry。返回加载统计。

    幂等：进程内只加载一次。
    """
    global _loaded
    stats = {"hooks": 0, "mcp_sources": 0}
    if _loaded:
        return stats
    _loaded = True

    base = Path(config_dir)

    # Hooks
    try:
        from src.core.hooks import load_hooks_from_config

        stats["hooks"] = load_hooks_from_config(base / "hooks.yaml", tool_registry.hooks)
    except Exception:
        pass

    # MCP 工具源
    try:
        from src.tools.mcp_adapter import load_mcp_sources_from_config

        for source in load_mcp_sources_from_config(str(base / "mcp.yaml")):
            tool_registry.add_source(source)
            stats["mcp_sources"] += 1
    except Exception:
        pass

    return stats


def reset_load_flag() -> None:
    """重置加载标记（供测试使用）"""
    global _loaded
    tool_registry.shutdown_sources()
    _loaded = False


def shutdown_extensions() -> None:
    """Close MCP/background resources and allow a clean later reload."""
    reset_load_flag()
