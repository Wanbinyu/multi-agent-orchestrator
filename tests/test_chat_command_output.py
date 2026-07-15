"""CLI 流式过程输出测试。"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.cli.chat_command import _stream_turn
from src.models.schemas import ChatStreamEvent


class _FakeAgent:
    def __init__(self):
        self.gateway = MagicMock()
        self.gateway.get_main_model.return_value = "main-model"

    @staticmethod
    def _has_tool_calls(content: str) -> bool:
        return "```tool:" in content

    async def run_turn_stream(self, _user_input: str):
        call = {
            "tool": "read_file",
            "params": {"path": "G:/demo/README.md"},
            "success": True,
        }
        yield ChatStreamEvent(
            type="delta",
            delta='```tool:read_file\n{"path":"G:/demo/README.md"}\n```',
        )
        yield ChatStreamEvent(
            type="tool_start",
            tool_call={"tool": call["tool"], "params": call["params"]},
        )
        yield ChatStreamEvent(type="tool_complete", tool_call=call)
        yield ChatStreamEvent(
            type="done",
            assistant_message="这是最终重构方案。",
            tool_calls=[call],
            files_written=["sessions/demo/output/response.md"],
            input_tokens=100,
            output_tokens=20,
            cost_usd=0.01,
        )


def test_stream_turn_prints_final_answer_and_compact_work_summary(capsys):
    asyncio.run(_stream_turn(_FakeAgent(), "分析项目"))

    output = capsys.readouterr().out
    assert "探索项目" in output
    assert "读取文件 G:/demo/README.md" in output
    assert "这是最终重构方案" in output
    assert "本轮工作" in output
    assert "交付文件" in output
    assert "Read(G:/demo/README.md)" not in output
