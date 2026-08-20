"""P0-1 single-Agent edit-run-fix loop against real pytest fixtures."""
from __future__ import annotations

from src.core.agent import Agent
from src.core.session import Session
from src.models.schemas import ChatResponse
from unittest.mock import MagicMock


def _session(tmp_path) -> Session:
    return Session(
        id="fix-session",
        title="t",
        created_at="2026-08-19T00:00:00+00:00",
        updated_at="2026-08-19T00:00:00+00:00",
        output_dir=str(tmp_path / "output"),
    )


def _gateway(*responses: str) -> MagicMock:
    gateway = MagicMock()
    gateway.main_model = None
    gateway.chat_with_main_model.side_effect = [
        ChatResponse(
            content=text,
            model="glm",
            provider="ark",
            input_tokens=8,
            output_tokens=4,
            cost_usd=0.0001,
        )
        for text in responses
    ]
    return gateway


def _write_fixture(root) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "app.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (root / "test_app.py").write_text(
        "import unittest\nfrom app import add\n\n"
        "class AddTests(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(1, 2), 3)\n",
        encoding="utf-8",
    )
    (root / "test_other.py").write_text(
        "import unittest\n\nclass OtherTests(unittest.TestCase):\n"
        "    def test_other(self):\n"
        "        self.assertTrue(True)\n",
        encoding="utf-8",
    )


def test_single_file_fix_passes_within_bound(tmp_path):
    session = _session(tmp_path)
    _write_fixture(tmp_path / "output")
    verify = (
        '```tool:run_command\n'
        '{"command":"python -B -m unittest test_app.py test_other.py","cwd":"."}\n```'
    )
    gateway = _gateway(
        '```tool:write_file\n'
        '{"path":"app.py","content":"def add(a, b):\\n    return a - b\\n"}\n```\n'
        + verify,
        '```tool:write_file\n'
        '{"path":"app.py","content":"def add(a, b):\\n    return a + b\\n"}\n```\n'
        + verify,
        "修复完成",
    )
    agent = Agent(gateway, session, approval_mode="auto", max_fix_rounds=3)

    result = agent.run_turn("修复 app.py 的加法错误")

    assert result.engineering["metrics"]["collaboration_triggered"] is False
    assert result.engineering["metrics"]["fix_round"] >= 1
    assert result.engineering["metrics"]["bounded_fix"]["status"] == "passed"
    assert result.engineering["status"] == "completed"
    assert result.engineering["audit"]["status"] == "passed"
    assert (tmp_path / "output" / "app.py").read_text(encoding="utf-8").count("a + b") == 1


def test_fix_round_limit_blocks_and_does_not_fake_complete(tmp_path):
    session = _session(tmp_path)
    _write_fixture(tmp_path / "output")
    wrong = (
        '```tool:edit_file\n'
        '{"path":"app.py","old_string":"return a - b","new_string":"return a * b"}\n```\n'
        '```tool:run_command\n'
        '{"command":"python -B -m unittest test_app.py"}\n```'
    )
    gateway = _gateway(wrong, wrong, wrong, "不应再调用")
    agent = Agent(gateway, session, approval_mode="auto", max_fix_rounds=2)

    result = agent.run_turn("修复 app.py 的加法错误")

    assert result.engineering["metrics"]["fix_round"] == 2
    assert result.engineering["metrics"]["bounded_fix"]["status"] == "blocked"
    assert result.engineering["status"] == "blocked"
    assert result.engineering["audit"]["can_complete"] is False
    assert "有界修复已达" in result.assistant_message
    assert gateway.chat_with_main_model.call_count == 2
    assert "a * b" in (tmp_path / "output" / "app.py").read_text(encoding="utf-8")
