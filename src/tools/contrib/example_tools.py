"""示例贡献工具：word_count

演示第三方如何为 MAO 添加新工具。这是一个纯只读、无外部依赖的小工具，
可作为模板复制改造。
"""
from __future__ import annotations

from src.tools.registry import tool_registry
from src.tools.tool_result import ToolResult


@tool_registry.register(
    name="word_count",
    description="统计给定文本的字符数、单词数、行数",
    params={
        "text": {"type": "string", "description": "要统计的文本"},
    },
    category="read",
)
def word_count(text: str, base_dir: str = ".") -> ToolResult:
    """统计文本的字符数、单词数、行数"""
    try:
        if not isinstance(text, str):
            return ToolResult(success=False, error="text 必须是字符串")
        chars = len(text)
        words = len(text.split())
        lines = text.count("\n") + (1 if text.strip() else 0)
        return ToolResult(
            success=True,
            output=f"字符数：{chars}\n单词数：{words}\n行数：{lines}",
        )
    except Exception as e:
        return ToolResult(success=False, error=str(e))
