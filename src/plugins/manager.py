"""Plugin manager: discover, enable-gate, isolate-load and shut down plugins.

Discovery uses the Python entry-point group ``mao.plugins``; MAO never
scans arbitrary workspace code. Plugins are disabled by default and only
loaded after the user explicitly enables them in ``config/plugins.yaml``.

Each plugin's ``load`` runs in its own try/except. A failing plugin is
rolled back (its ``PluginContext.rollback`` undoes its registrations)
and reported as a diagnostic; it never blocks other plugins or a
pluginless startup.
"""
from __future__ import annotations

import importlib.metadata
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import yaml

from src.plugins.api import (
    Plugin,
    PluginContext,
    PluginManifest,
    is_supported_api_version,
)
from src.tools.extension_diagnostics import (
    ExtensionDiagnostic,
    bounded_diagnostics,
    make_extension_diagnostic,
)

ENTRY_POINT_GROUP = "mao.plugins"

EntryPointFinder = Callable[[], "Iterable[importlib.metadata.EntryPoint]"]


def _default_entry_points() -> "Iterable[importlib.metadata.EntryPoint]":
    try:
        return importlib.metadata.entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - 极旧 Python 无 group kw
        return importlib.metadata.entry_points().get(ENTRY_POINT_GROUP, [])


def _is_plugin(obj: Any) -> bool:
    """Duck-typed Plugin 协议判定（manifest + load + shutdown）。"""
    manifest = getattr(obj, "manifest", None)
    return (
        isinstance(manifest, PluginManifest)
        and callable(getattr(obj, "load", None))
        and callable(getattr(obj, "shutdown", None))
    )


@dataclass
class DiscoveredPlugin:
    """经 entry point 发现、尚未决定启用的插件。"""

    plugin: Plugin
    manifest: PluginManifest
    dist_name: str
    entry_point: str
    api_compatible: bool

    def to_status(self, enabled: bool) -> dict[str, Any]:
        return {
            "id": self.manifest.id,
            "name": self.manifest.name,
            "version": self.manifest.version,
            "mao_api_version": self.manifest.mao_api_version,
            "api_compatible": self.api_compatible,
            "enabled": enabled,
            "capabilities": list(self.manifest.capabilities),
            "permissions": list(self.manifest.permissions),
            "description": self.manifest.description,
            "homepage": self.manifest.homepage,
            "source": self.dist_name or self.manifest.source,
        }


@dataclass
class PluginLoadResult:
    discovered: int = 0
    loaded: int = 0
    rejected_incompatible: int = 0
    skipped_disabled: int = 0
    failed: int = 0
    diagnostics: list[ExtensionDiagnostic] = field(default_factory=list)
    loaded_ids: list[str] = field(default_factory=list)

    def to_summary(self) -> dict[str, Any]:
        return {
            "discovered": self.discovered,
            "loaded": self.loaded,
            "rejected_incompatible": self.rejected_incompatible,
            "skipped_disabled": self.skipped_disabled,
            "failed": self.failed,
            "loaded_ids": list(self.loaded_ids),
            "diagnostics": list(self.diagnostics),
        }


class PluginManager:
    """管理插件发现、启用门控、隔离加载与关闭。"""

    def __init__(
        self,
        tool_registry: Any,
        preset_registry: Any = None,
        config_dir: str | Path = "config",
        entry_points_finder: EntryPointFinder | None = None,
    ) -> None:
        self._tool_registry = tool_registry
        self._preset_registry = preset_registry
        self._config_dir = Path(config_dir)
        self._entry_points_finder = entry_points_finder or _default_entry_points
        self._discovered: list[DiscoveredPlugin] = []
        self._plugins: dict[str, Plugin] = {}
        self._contexts: dict[str, PluginContext] = {}
        self._last_result: PluginLoadResult = PluginLoadResult()
        self._loaded = False

    # ---------- 发现 ----------

    def discover(self) -> list[DiscoveredPlugin]:
        """通过 ``mao.plugins`` entry point 组发现插件。"""
        discovered: list[DiscoveredPlugin] = []
        diagnostics: list[ExtensionDiagnostic] = []
        try:
            eps = list(self._entry_points_finder())
        except Exception as exc:
            self._discovered = discovered
            self._last_result = PluginLoadResult(
                diagnostics=[
                    make_extension_diagnostic(
                        source="plugin",
                        code="plugin_discovery_error",
                        message="插件 entry point 发现失败",
                        action="检查 MAO 安装与 Python 环境",
                        error=exc,
                    )
                ]
            )
            return discovered

        for ep in eps:
            try:
                factory = ep.load()
                plugin = factory() if callable(factory) else factory
                if not _is_plugin(plugin):
                    raise TypeError("entry point 未返回符合 Plugin 协议的对象")
                manifest = plugin.manifest
                dist = getattr(ep, "dist", None)
                dist_name = getattr(dist, "name", "") or ""
                discovered.append(
                    DiscoveredPlugin(
                        plugin=plugin,
                        manifest=manifest,
                        dist_name=dist_name,
                        entry_point=f"{ep.group}:{ep.name}",
                        api_compatible=is_supported_api_version(manifest.mao_api_version),
                    )
                )
            except Exception as exc:
                diagnostics.append(
                    make_extension_diagnostic(
                        source="plugin",
                        code="plugin_discover_error",
                        message=f"插件 {ep.value} 发现失败，已跳过",
                        action="检查该插件的 entry point 与 manifest",
                        entry=ep.value,
                        error=exc,
                    )
                )

        # 同 id 去重：保留第一个
        seen: set[str] = set()
        deduped: list[DiscoveredPlugin] = []
        for dp in discovered:
            if dp.manifest.id in seen:
                continue
            seen.add(dp.manifest.id)
            deduped.append(dp)

        self._discovered = deduped
        self._last_result = PluginLoadResult(
            discovered=len(deduped), diagnostics=bounded_diagnostics(diagnostics)
        )
        return deduped

    def discovered(self) -> list[DiscoveredPlugin]:
        """返回最近一次发现的列表（惰性发现）。"""
        if not self._discovered:
            self.discover()
        return list(self._discovered)

    # ---------- 启用态 ----------

    def _config_path(self) -> Path:
        return self._config_dir / "plugins.yaml"

    def _read_enable_config(self) -> tuple[set[str], set[str]]:
        path = self._config_path()
        if not path.exists():
            return set(), set()
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except Exception:
            return set(), set()
        if not isinstance(data, dict):
            return set(), set()
        enabled = {str(x) for x in (data.get("enabled") or [])}
        disabled = {str(x) for x in (data.get("disabled") or [])}
        return enabled, disabled

    def _write_enable_config(self, enabled: set[str], disabled: set[str]) -> None:
        self._config_dir.mkdir(parents=True, exist_ok=True)
        data = {"enabled": sorted(enabled), "disabled": sorted(disabled)}
        self._config_path().write_text(
            yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )

    def is_enabled(self, plugin_id: str) -> bool:
        enabled, disabled = self._read_enable_config()
        if plugin_id in disabled:
            return False
        return plugin_id in enabled

    def enable(self, plugin_id: str) -> bool:
        enabled, disabled = self._read_enable_config()
        disabled.discard(plugin_id)
        enabled.add(plugin_id)
        self._write_enable_config(enabled, disabled)
        return True

    def disable(self, plugin_id: str) -> bool:
        enabled, disabled = self._read_enable_config()
        enabled.discard(plugin_id)
        disabled.add(plugin_id)
        self._write_enable_config(enabled, disabled)
        return True

    # ---------- 加载 ----------

    def load_enabled(self) -> PluginLoadResult:
        """加载已发现、已启用且 API 兼容的插件。幂等：进程内只加载一次。"""
        if self._loaded:
            return self._last_result
        self._loaded = True

        if not self._discovered:
            self.discover()

        result = PluginLoadResult(discovered=len(self._discovered))
        enabled, disabled = self._read_enable_config()

        for dp in self._discovered:
            pid = dp.manifest.id
            if not dp.api_compatible:
                result.rejected_incompatible += 1
                result.diagnostics.append(
                    make_extension_diagnostic(
                        source="plugin",
                        code="plugin_api_incompatible",
                        message=(
                            f"插件 {pid} 的 API 版本 {dp.manifest.mao_api_version} 不兼容，已拒绝"
                        ),
                        action=f"升级插件或等待 MAO 支持 API {dp.manifest.mao_api_version}",
                        entry=pid,
                    )
                )
                continue
            if pid in disabled or pid not in enabled:
                result.skipped_disabled += 1
                continue

            ctx = PluginContext(self._tool_registry, preset_registry=self._preset_registry)
            try:
                dp.plugin.load(ctx)
            except Exception as exc:
                result.failed += 1
                # 回滚已注册的部分，避免半加载状态污染注册表
                try:
                    ctx.rollback()
                except Exception:
                    pass
                result.diagnostics.append(
                    make_extension_diagnostic(
                        source="plugin",
                        code="plugin_load_error",
                        message=f"插件 {pid} 加载失败，已隔离",
                        action="查看插件日志或禁用该插件",
                        entry=pid,
                        error=exc,
                    )
                )
                continue

            self._plugins[pid] = dp.plugin
            self._contexts[pid] = ctx
            result.loaded += 1
            result.loaded_ids.append(pid)

        result.diagnostics = bounded_diagnostics(result.diagnostics)
        self._last_result = result
        return result

    def last_result(self) -> PluginLoadResult:
        return self._last_result

    def list_status(self) -> list[dict[str, Any]]:
        """返回所有已发现插件的状态（供 CLI/Web 展示）。"""
        statuses: list[dict[str, Any]] = []
        for dp in self.discovered():
            statuses.append(dp.to_status(enabled=self.is_enabled(dp.manifest.id)))
        return statuses

    def loaded_plugins(self) -> dict[str, Plugin]:
        return dict(self._plugins)

    # ---------- 关闭 ----------

    def shutdown(self) -> None:
        """逐个关闭已加载插件并注销其贡献（best-effort）。"""
        for pid, plugin in list(self._plugins.items()):
            try:
                plugin.shutdown()
            except Exception:
                pass
            ctx = self._contexts.pop(pid, None)
            if ctx is not None:
                try:
                    ctx.rollback()
                except Exception:
                    pass
        self._plugins.clear()
        self._contexts.clear()
        self._loaded = False

    def reset(self) -> None:
        """重置发现与加载态（供测试使用）。"""
        self.shutdown()
        self._discovered = []
        self._last_result = PluginLoadResult()
        self._loaded = False
