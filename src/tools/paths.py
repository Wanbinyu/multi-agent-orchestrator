"""共享路径解析工具"""
from __future__ import annotations

from pathlib import Path


def resolve_path(path: str, base_dir: str) -> Path:
    """解析路径：绝对路径直接使用；相对路径限制在 base_dir 内，防止目录穿越"""
    target = Path(path)
    if target.is_absolute():
        return target.resolve()

    base = Path(base_dir).resolve()
    resolved = (base / path).resolve()
    try:
        resolved.relative_to(base)
    except ValueError as exc:
        raise ValueError(f"路径越界：{path}") from exc
    return resolved
