"""示例 MAO 插件：贡献一个只读 ``word_count`` 工具。

演示 Plugin API v0 的完整打包方式：独立 Python 包，通过
``mao.plugins`` entry point 被发现，manifest 声明能力与权限，``load``
注册工具，``shutdown`` 清理。安装后用 ``mao plugin enable mao-wordcount``
启用，下次启动 ``mao`` 即加载。
"""
from __future__ import annotations

from src.plugins.api import (
    CAP_TOOLS,
    MAO_PLUGIN_API_VERSION,
    PERM_READ_FILES,
    Plugin,
    PluginContext,
    PluginManifest,
)
from src.tools.tool_result import ToolResult


def word_count(text: str = "", base_dir: str = ".") -> ToolResult:
    """统计给定文本的字符数、单词数、行数。"""
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
    except Exception as exc:
        return ToolResult(success=False, error=str(exc))


class WordCountPlugin:
    """Plugin 协议实现：注册 word_count 工具。"""

    def __init__(self) -> None:
        self.manifest = PluginManifest(
            id="mao-wordcount",
            name="Word Count",
            version="0.1.0",
            mao_api_version=MAO_PLUGIN_API_VERSION,
            description="贡献一个统计字符/单词/行数的只读工具",
            homepage="https://github.com/Wanbinyu/multi-agent-orchestrator",
            capabilities=[CAP_TOOLS],
            permissions=[PERM_READ_FILES],
            source="mao-wordcount-plugin",
        )

    def load(self, ctx: PluginContext) -> None:
        ctx.register_tool(
            word_count,
            name="word_count",
            description="统计给定文本的字符数、单词数、行数",
            params={"text": {"type": "string", "description": "要统计的文本"}},
            category="read",
        )

    def shutdown(self) -> None:
        pass


def create_plugin() -> Plugin:
    """``mao.plugins`` entry point 工厂：返回插件实例。"""
    return WordCountPlugin()
