"""进程级插件运行时：单例管理器 + 加载/关闭钩子。

镜像 ``src.tools.extensions``：``load_plugins()`` 幂等，可在 CLI 对话与
Web 启动时调用；``shutdown_plugins()`` 清理。CLI 的 ``mao plugin`` 子命令
使用独立的新管理器实例，避免影响运行中的工具注册表。
"""
from __future__ import annotations

from src.plugins.manager import PluginManager, PluginLoadResult
from src.tools.registry import tool_registry

_manager: PluginManager | None = None


def _new_manager(config_dir: str = "config", preset_registry=None) -> PluginManager:
    """构建一个新的 PluginManager（不复用单例）。"""
    if preset_registry is None:
        try:
            import src.ui.presets as presets  # noqa: F401

            preset_registry = presets
        except Exception:
            preset_registry = None
    return PluginManager(
        tool_registry, preset_registry=preset_registry, config_dir=config_dir
    )


def new_plugin_manager(config_dir: str = "config") -> PluginManager:
    """供 CLI 子命令使用的新管理器（独立于启动单例）。"""
    return _new_manager(config_dir)


def get_plugin_manager(config_dir: str = "config") -> PluginManager:
    """返回启动用单例（首次调用时构建）。"""
    global _manager
    if _manager is None:
        _manager = _new_manager(config_dir)
    return _manager


def load_plugins(config_dir: str = "config") -> PluginLoadResult:
    """发现并加载已启用插件到当前工具注册表。幂等。"""
    return get_plugin_manager(config_dir).load_enabled()


def get_plugin_status() -> dict:
    """返回插件状态（供 Web/CLI 展示）。"""
    mgr = _manager
    if mgr is None:
        return {"statuses": [], "load": None}
    return {"statuses": mgr.list_status(), "load": mgr.last_result().to_summary()}


def shutdown_plugins() -> None:
    """关闭已加载插件并注销其贡献。"""
    global _manager
    if _manager is not None:
        _manager.shutdown()
        _manager = None
