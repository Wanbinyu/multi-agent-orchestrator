"""CLI 流式过程输出测试。"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from src.cli import chat_command
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


class _FailedReviewAgent(_FakeAgent):
    async def run_turn_stream(self, _user_input: str):
        yield ChatStreamEvent(
            type="plan",
            plan={"summary": "只读分析", "tasks": []},
        )
        yield ChatStreamEvent(
            type="task_retry",
            task={
                "id": "test",
                "type": "tester",
                "title": "运行测试",
                "attempt": 2,
                "max_attempts": 2,
                "previous_error": "connection timeout",
            },
        )
        yield ChatStreamEvent(
            type="review_complete",
            review={"passed": False, "issues": ["缺少测试"]},
        )
        yield ChatStreamEvent(
            type="done",
            assistant_message="请补充测试后再实施。",
            input_tokens=10,
            output_tokens=5,
        )


def test_stream_turn_handles_failed_review_without_markup_error(capsys):
    asyncio.run(_stream_turn(_FailedReviewAgent(), "只做方案"))
    output = capsys.readouterr().out
    assert "审查结果：未通过" in output
    assert "缺少测试" in output
    assert "定向重试 2/2" in output
    assert "connection timeout" in output
    assert "请补充测试后再实施" in output


class _EngineeringEventAgent(_FakeAgent):
    async def run_turn_stream(self, _user_input: str):
        yield ChatStreamEvent(
            type="engineering_start",
            engineering={
                "run_id": "run-test",
                "status": "running",
                "intent": {
                    "kind": "review",
                    "risk_level": "medium",
                    "write_authorized": False,
                    "policy": {"allow_project_writes": False},
                },
            },
        )
        yield ChatStreamEvent(type="delta", delta="完成")
        yield ChatStreamEvent(
            type="engineering_complete",
            engineering={
                "run_id": "run-test",
                "status": "completed",
                "evidence_count": 3,
                "reconnaissance": {
                    "status": "partial",
                    "observed_categories": ["structure", "docs"],
                },
                "verification_count": 1,
                "audit": {
                    "status": "blocked",
                    "missing_checks": ["相邻模块回归"],
                    "failed_checks": [],
                },
            },
        )
        yield ChatStreamEvent(type="done", assistant_message="完成")


def test_stream_turn_prints_engineering_run_status(capsys):
    asyncio.run(_stream_turn(_EngineeringEventAgent(), "执行任务"))
    output = capsys.readouterr().out
    assert "工程记录：run-test · completed" in output
    assert "review / medium / 只读" in output
    assert "证据：3 条" in output
    assert "项目侦察：部分覆盖（2/6）" in output
    assert "验证门：1 个" in output
    assert "完成审计：未闭环" in output
    assert "缺口：相邻模块回归" in output


class _PlainStreamingAgent(_FakeAgent):
    async def run_turn_stream(self, _user_input: str):
        yield ChatStreamEvent(type="delta", delta="关于上下文")
        yield ChatStreamEvent(type="delta", delta="与自动压缩")
        yield ChatStreamEvent(
            type="done",
            assistant_message="关于上下文与自动压缩",
            input_tokens=2,
            output_tokens=4,
        )


def test_plain_stream_uses_transient_bounded_preview_and_prints_final_once(
    monkeypatch,
    capsys,
):
    created: dict = {}

    class _RecordingLive:
        def __init__(self, _renderable, **kwargs):
            created.update(kwargs)

        def start(self):
            return None

        def stop(self):
            return None

        def update(self, _renderable):
            return None

    monkeypatch.setattr(chat_command, "Live", _RecordingLive)

    asyncio.run(_stream_turn(_PlainStreamingAgent(), "询问上下文"))

    output = capsys.readouterr().out
    assert created["transient"] is True
    assert created["vertical_overflow"] == "ellipsis"
    assert output.count("关于上下文与自动压缩") == 1
