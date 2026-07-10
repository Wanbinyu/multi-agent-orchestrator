"""Reviewer 单元测试"""
from unittest.mock import MagicMock

import pytest

from src.core.reviewer import Reviewer
from src.models.schemas import ChatResponse, ReviewResult, Task, TaskPlan, TaskResult


def _mock_gateway(response_content: str) -> MagicMock:
    gateway = MagicMock()
    gateway.chat.return_value = ChatResponse(
        content=response_content,
        model="glm-ark",
        provider="ark",
        input_tokens=100,
        output_tokens=50,
        cost_usd=0.0001,
    )
    return gateway


def _sample_plan() -> TaskPlan:
    return TaskPlan(
        summary="写一个登录页面",
        tasks=[
            Task(
                id="t1",
                type="frontend",
                title="编写 HTML",
                input="写一个登录页面 HTML",
                assigned_model="glm-ark",
            )
        ],
    )


def _sample_results() -> list[TaskResult]:
    return [
        TaskResult(
            task=_sample_plan().tasks[0],
            success=True,
            content="```html\n<input>\n```",
            response=ChatResponse(
                content="```html\n<input>\n```",
                model="glm-ark",
                provider="ark",
                input_tokens=10,
                output_tokens=5,
                cost_usd=0.00001,
            ),
            files_written=["output/frontend_t1/generated_1.html"],
        )
    ]


def test_reviewer_parses_json_output(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    # 创建最小 workers.yaml
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        "reviewer:\n  model: glm-ark\n  system_prompt: test\n",
        encoding="utf-8",
    )

    gateway = _mock_gateway(
        '{"passed": true, "issues": [], "final_output": "整合后的登录页面 HTML"}'
    )

    reviewer = Reviewer(gateway, config_path=str(config_path))
    result = reviewer.review("写一个登录页面", _sample_plan(), _sample_results())

    assert isinstance(result, ReviewResult)
    assert result.passed is True
    assert result.issues == []
    assert result.final_output == "整合后的登录页面 HTML"
    gateway.chat.assert_called_once()


def test_reviewer_parses_json_in_code_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")

    gateway = _mock_gateway(
        '```json\n{"passed": false, "issues": ["缺少提交按钮"], "final_output": "需要加按钮"}\n```'
    )

    reviewer = Reviewer(gateway, config_path=str(config_path))
    result = reviewer.review("写一个登录页面", _sample_plan(), _sample_results())

    assert result.passed is False
    assert result.issues == ["缺少提交按钮"]
    assert result.final_output == "需要加按钮"


def test_reviewer_fallback_for_non_json(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")

    gateway = _mock_gateway("这是纯文本输出，没有 JSON。")

    reviewer = Reviewer(gateway, config_path=str(config_path))
    result = reviewer.review("写一个登录页面", _sample_plan(), _sample_results())

    assert result.passed is True
    assert result.final_output == "这是纯文本输出，没有 JSON。"
