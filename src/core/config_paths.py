"""运行配置路径解析，优先本地私有配置并回退到无密钥示例。"""
from __future__ import annotations

from pathlib import Path


def resolve_workers_config_path(path: str | Path = "config/workers.yaml") -> Path:
    target = Path(path)
    if target.exists():
        return target
    if target.name == "workers.yaml":
        example = target.with_name("workers.yaml.example")
        if example.exists():
            return example
    return target
