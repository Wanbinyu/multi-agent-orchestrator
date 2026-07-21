"""MAO Plugin API v0.

Stable interface for MAO plugins. A plugin is discovered via the Python
entry-point group ``mao.plugins``; each entry point points to a factory
``() -> Plugin``. Plugins are disabled by default and only loaded after
the user explicitly enables them in ``config/plugins.yaml``.

Python plugins run as trusted local code with the same privileges as the
MAO process. The permission list is a consent surface shown to the user,
not a sandbox.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

if TYPE_CHECKING:
    from src.tools.registry import ToolRegistry, ToolSource


MAO_PLUGIN_API_VERSION = "0.1"
SUPPORTED_API_VERSIONS = frozenset({"0.1"})

# 插件可声明的能力（决定它能调用 PluginContext 的哪些注册方法）
CAP_TOOLS = "tools"
CAP_TOOL_SOURCE = "tool_source"
CAP_HOOKS = "hooks"
CAP_PROVIDER_PRESET = "provider_preset"
CAP_MODEL_CAPABILITIES = "model_capabilities"
KNOWN_CAPABILITIES = frozenset(
    {
        CAP_TOOLS,
        CAP_TOOL_SOURCE,
        CAP_HOOKS,
        CAP_PROVIDER_PRESET,
        CAP_MODEL_CAPABILITIES,
    }
)

# 插件声明的权限（仅声明与展示，用户启用即同意；不构成沙箱）
PERM_READ_FILES = "read_files"
PERM_WRITE_FILES = "write_files"
PERM_EXECUTE = "execute"
PERM_NETWORK = "network"
KNOWN_PERMISSIONS = frozenset(
    {PERM_READ_FILES, PERM_WRITE_FILES, PERM_EXECUTE, PERM_NETWORK}
)

_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*$")


def is_supported_api_version(version: str) -> bool:
    """插件声明的 MAO API 版本是否可加载。"""
    return version in SUPPORTED_API_VERSIONS


@dataclass
class PluginManifest:
    """插件清单：唯一标识、版本、API 兼容、能力与权限。"""

    id: str
    name: str
    version: str
    mao_api_version: str
    description: str = ""
    homepage: str = ""
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    source: str = ""  # 发行包/entry point 来源（诊断用）

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not _ID_PATTERN.match(self.id):
            raise ValueError(
                f"插件 id 非法（需匹配 {_ID_PATTERN.pattern}）：{self.id!r}"
            )
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("插件 name 不能为空")
        if not isinstance(self.version, str) or not self.version.strip():
            raise ValueError("插件 version 不能为空")
        if not isinstance(self.mao_api_version, str) or not self.mao_api_version.strip():
            raise ValueError("插件 mao_api_version 不能为空")
        bad_caps = set(self.capabilities) - KNOWN_CAPABILITIES
        if bad_caps:
            raise ValueError(f"未知能力：{sorted(bad_caps)}")
        bad_perms = set(self.permissions) - KNOWN_PERMISSIONS
        if bad_perms:
            raise ValueError(f"未知权限：{sorted(bad_perms)}")


class PluginContext:
    """插件 ``load`` 时获得的注册面。

    记录插件的所有贡献，供管理器在加载失败时回滚或在禁用时清理。
    """

    def __init__(
        self,
        tool_registry: "ToolRegistry",
        preset_registry: Any = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._preset_registry = preset_registry
        self._tools: list[str] = []
        self._sources: list["ToolSource"] = []
        self._pre_hooks: list[Callable] = []
        self._post_hooks: list[Callable] = []
        self._presets: list[str] = []
        self._model_capabilities: dict[str, dict[str, Any]] = {}

    def register_tool(
        self,
        fn: Callable[..., Any],
        *,
        name: str,
        description: str,
        params: dict[str, Any] | None = None,
        category: str = "read",
    ) -> None:
        """注册一个本地工具到工具注册表。"""
        self._tool_registry.register_function(
            fn,
            name=name,
            description=description,
            params=params or {},
            category=category,
        )
        self._tools.append(name)

    def add_tool_source(self, source: "ToolSource") -> None:
        """挂载一个外部工具源（如 MCP 适配器）。"""
        self._tool_registry.add_source(source)
        self._sources.append(source)

    def add_pre_hook(self, fn: Callable[..., Any]) -> None:
        """注册工具执行前钩子。"""
        self._tool_registry.add_pre_hook(fn)
        self._pre_hooks.append(fn)

    def add_post_hook(self, fn: Callable[..., Any]) -> None:
        """注册工具执行后钩子。"""
        self._tool_registry.add_post_hook(fn)
        self._post_hooks.append(fn)

    def register_provider_preset(self, key: str, preset: dict[str, Any]) -> None:
        """贡献一个 WebUI Provider 预设。"""
        if self._preset_registry is None:
            raise RuntimeError("当前环境不支持注册 Provider 预设")
        self._preset_registry.register_preset(key, preset)
        self._presets.append(key)

    def register_model_capabilities(self, alias: str, data: dict[str, Any]) -> None:
        """贡献模型能力数据。v0 仅记录，目录合并能力有限。"""
        self._model_capabilities[alias] = dict(data)

    @property
    def model_capabilities(self) -> dict[str, dict[str, Any]]:
        return dict(self._model_capabilities)

    def contributed_summary(self) -> dict[str, int]:
        """返回本上下文记录的贡献计数（诊断/展示用）。"""
        return {
            "tools": len(self._tools),
            "tool_sources": len(self._sources),
            "pre_hooks": len(self._pre_hooks),
            "post_hooks": len(self._post_hooks),
            "presets": len(self._presets),
            "model_capabilities": len(self._model_capabilities),
        }

    def rollback(self) -> None:
        """撤销本上下文记录的全部贡献（best-effort，加载失败时调用）。"""
        for name in reversed(self._tools):
            self._tool_registry.unregister_tool(name)
        for source in self._sources:
            self._tool_registry.remove_source(source)
            shutdown = getattr(source, "shutdown", None)
            if callable(shutdown):
                try:
                    shutdown()
                except Exception:
                    pass
        for fn in self._pre_hooks:
            self._tool_registry.hooks.remove_pre(fn)
        for fn in self._post_hooks:
            self._tool_registry.hooks.remove_post(fn)
        if self._preset_registry is not None:
            for key in self._presets:
                unregister = getattr(self._preset_registry, "unregister_preset", None)
                if callable(unregister):
                    unregister(key)
        self._tools.clear()
        self._sources.clear()
        self._pre_hooks.clear()
        self._post_hooks.clear()
        self._presets.clear()
        self._model_capabilities.clear()


class Plugin(Protocol):
    """MAO 插件协议：实现 ``manifest``、``load`` 与 ``shutdown``。"""

    manifest: PluginManifest

    def load(self, ctx: PluginContext) -> None:
        """注册贡献。抛异常则管理器回滚并隔离该插件。"""
        ...

    def shutdown(self) -> None:
        """释放插件自有的后台资源（工具/钩子/预设由管理器统一注销）。"""
        ...
