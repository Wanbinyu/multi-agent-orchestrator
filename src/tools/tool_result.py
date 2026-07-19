"""工具执行结果基类"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    output: str = ""
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
