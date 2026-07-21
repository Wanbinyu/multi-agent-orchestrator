"""MAO Plugin API v0 包。

公共接口见 :mod:`src.plugins.api`。插件管理器见 :mod:`src.plugins.manager`。
"""
from __future__ import annotations

from src.plugins.api import (
    CAP_HOOKS,
    CAP_MODEL_CAPABILITIES,
    CAP_PROVIDER_PRESET,
    CAP_TOOL_SOURCE,
    CAP_TOOLS,
    KNOWN_CAPABILITIES,
    KNOWN_PERMISSIONS,
    MAO_PLUGIN_API_VERSION,
    PERM_EXECUTE,
    PERM_NETWORK,
    PERM_READ_FILES,
    PERM_WRITE_FILES,
    SUPPORTED_API_VERSIONS,
    Plugin,
    PluginContext,
    PluginManifest,
    is_supported_api_version,
)

__all__ = [
    "CAP_HOOKS",
    "CAP_MODEL_CAPABILITIES",
    "CAP_PROVIDER_PRESET",
    "CAP_TOOL_SOURCE",
    "CAP_TOOLS",
    "KNOWN_CAPABILITIES",
    "KNOWN_PERMISSIONS",
    "MAO_PLUGIN_API_VERSION",
    "PERM_EXECUTE",
    "PERM_NETWORK",
    "PERM_READ_FILES",
    "PERM_WRITE_FILES",
    "SUPPORTED_API_VERSIONS",
    "Plugin",
    "PluginContext",
    "PluginManifest",
    "is_supported_api_version",
]
