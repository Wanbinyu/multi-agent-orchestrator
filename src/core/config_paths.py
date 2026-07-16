"""运行配置路径解析，优先本地私有配置并回退到无密钥示例。"""
from __future__ import annotations

from pathlib import Path


def _resolve_config_with_example(path: str | Path, canonical_name: str) -> Path:
    """Prefer a private config file; fall back to the committed *.example seed."""
    target = Path(path)
    if target.exists():
        return target
    if target.name == canonical_name:
        example = target.with_name(f"{canonical_name}.example")
        if example.exists():
            return example
    return target


def resolve_workers_config_path(path: str | Path = "config/workers.yaml") -> Path:
    return _resolve_config_with_example(path, "workers.yaml")


def resolve_providers_config_path(path: str | Path = "config/providers.yaml") -> Path:
    """Resolve providers config for fresh clones and CI (providers.yaml is gitignored)."""
    return _resolve_config_with_example(path, "providers.yaml")
