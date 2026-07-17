"""启动时加载扩展（Hooks + MCP 工具源）

从 config/ 目录读取 hooks.yaml 与 mcp.yaml，注册到全局 tool_registry。
配置缺失时静默跳过，不影响主流程。
"""
from __future__ import annotations

from pathlib import Path

from src.tools.extension_diagnostics import (
    ExtensionLoadResult,
    bounded_diagnostics,
    copy_extension_result,
    empty_extension_result,
    make_extension_diagnostic,
)
from src.tools.registry import tool_registry

_loaded = False
_last_result = empty_extension_result()


def load_extensions(config_dir: str = "config") -> ExtensionLoadResult:
    """加载 hooks 与 MCP 配置到全局 tool_registry。返回加载统计。

    幂等：进程内只加载一次。
    """
    global _loaded, _last_result
    if _loaded:
        return copy_extension_result(_last_result)
    _loaded = True
    stats = empty_extension_result()

    base = Path(config_dir)

    # Hooks
    try:
        from src.core.hooks import load_hooks_from_config_detailed

        stats["hooks"], diagnostics = load_hooks_from_config_detailed(
            base / "hooks.yaml", tool_registry.hooks
        )
        stats["diagnostics"].extend(diagnostics)
    except Exception as exc:
        stats["diagnostics"].append(
            make_extension_diagnostic(
                source="hooks",
                code="hook_loader_error",
                message="Hooks 加载器不可用，已跳过 Hooks",
                action="检查 MAO 安装和 Hooks 配置",
                config_path=base / "hooks.yaml",
                error=exc,
            )
        )

    # MCP 工具源
    try:
        from src.tools.mcp_adapter import load_mcp_sources_from_config_detailed

        sources, diagnostics = load_mcp_sources_from_config_detailed(
            str(base / "mcp.yaml")
        )
        stats["diagnostics"].extend(diagnostics)
        for source in sources:
            tool_registry.add_source(source)
            stats["mcp_sources"] += 1
    except Exception as exc:
        stats["diagnostics"].append(
            make_extension_diagnostic(
                source="mcp",
                code="mcp_loader_error",
                message="MCP 加载器不可用，已跳过 MCP",
                action="检查 MAO 安装和 MCP 配置",
                config_path=base / "mcp.yaml",
                error=exc,
            )
        )

    stats["diagnostics"] = bounded_diagnostics(stats["diagnostics"])
    _last_result = copy_extension_result(stats)
    return copy_extension_result(_last_result)


def get_extension_status() -> ExtensionLoadResult:
    """Return the latest process-local extension status without loading again."""
    return copy_extension_result(_last_result)


def reset_load_flag() -> None:
    """重置加载标记（供测试使用）"""
    global _loaded, _last_result
    tool_registry.shutdown_sources()
    _loaded = False
    _last_result = empty_extension_result()


def shutdown_extensions() -> None:
    """Close MCP/background resources and allow a clean later reload."""
    reset_load_flag()
