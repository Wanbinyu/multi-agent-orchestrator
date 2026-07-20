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


def test_reviewer_injects_project_rules(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")
    gateway = _mock_gateway(
        '{"passed": true, "issues": [], "final_output": "ok"}'
    )
    gateway.resolve_model.return_value = "glm-ark"

    reviewer = Reviewer(
        gateway,
        config_path=str(config_path),
        project_rules="PROJECT RULE SENTINEL",
    )
    reviewer.review("request", _sample_plan(), _sample_results())

    messages = gateway.chat.call_args.kwargs["messages"]
    assert "PROJECT RULE SENTINEL" in messages[0].content


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

    assert result.passed is False
    assert "不能自动通过" in result.issues[0]
    assert result.final_output == "这是纯文本输出，没有 JSON。"
    assert reviewer.last_response is gateway.chat.return_value


def test_reviewer_rejects_invalid_json_field_types(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")
    gateway = _mock_gateway(
        '{"passed": "false", "issues": "none", "final_output": {}}'
    )

    reviewer = Reviewer(gateway, config_path=str(config_path))
    result = reviewer.review("request", _sample_plan(), _sample_results())

    assert result.passed is False
    assert result.issues == ["Reviewer JSON 字段类型无效，不能自动通过"]
    assert reviewer.last_response is gateway.chat.return_value


def test_reviewer_cannot_override_failed_deterministic_audit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")
    gateway = _mock_gateway(
        '{"passed": true, "issues": [], "final_output": "全部完成"}'
    )
    reviewer = Reviewer(gateway, config_path=str(config_path))

    result = reviewer.review(
        "写一个登录页面",
        _sample_plan(),
        _sample_results(),
        engineering_context={
            "evidence": [],
            "verification": [],
            "audit": {
                "can_complete": False,
                "summary": "验证未闭环",
                "missing_checks": ["集成测试", "全量回归"],
                "failed_checks": [],
            },
        },
    )

    assert result.passed is False
    assert "确定性工程审计未通过：集成测试、全量回归" in result.issues
    prompt = gateway.chat.call_args.kwargs["messages"][1].content
    assert "确定性工程审计" in prompt
    assert "缺失检查：集成测试、全量回归" in prompt


def test_reviewer_receives_files_acceptance_and_real_command_evidence(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")
    gateway = _mock_gateway('{"passed": true, "issues": [], "final_output": "ok"}')
    result = _sample_results()[0]
    result.acceptance_evidence = ["前端闭包通过"]
    result.tool_calls = [{
        "tool": "run_command",
        "params": {"command": "npm run build"},
        "success": True,
        "output": "built",
        "metadata": {"cwd": str(tmp_path), "exit_code": 0},
    }]

    Reviewer(gateway, config_path=str(config_path)).review(
        "原始请求标记", _sample_plan(), [result]
    )

    prompt = gateway.chat.call_args.kwargs["messages"][1].content
    assert "原始请求标记" in prompt
    assert result.files_written[0] in prompt
    assert "前端闭包通过" in prompt
    assert "npm run build" in prompt
    assert "exit_code=0" in prompt


def test_reviewer_cannot_pass_when_a_worker_failed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")
    gateway = _mock_gateway('{"passed": true, "issues": [], "final_output": "ok"}')
    failed = _sample_results()[0]
    failed.success = False
    failed.error = "closure failed"

    review = Reviewer(gateway, config_path=str(config_path)).review(
        "request", _sample_plan(), [failed]
    )

    assert review.passed is False
    assert "存在失败的确定性子任务：t1" in review.issues


def test_restricted_reviewer_excludes_worker_body_but_keeps_direct_evidence(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        "reviewer:\n  model: glm-ark\n  input_mode: restricted\n",
        encoding="utf-8",
    )
    gateway = _mock_gateway('{"passed": true, "issues": [], "final_output": "ok"}')
    result = _sample_results()[0]
    result.content = "WORKER_SELF_REPORT_SENTINEL claims everything passed"
    result.response.content = "WORKER_RESPONSE_SENTINEL"
    result.acceptance_evidence = ["验证命令通过：npm test"]
    result.tool_calls = [{
        "tool": "run_command",
        "params": {"command": "npm test"},
        "success": True,
        "output": "12 passed",
        "metadata": {"cwd": str(tmp_path), "exit_code": 0},
    }]

    reviewer = Reviewer(gateway, config_path=str(config_path))
    reviewer.review(
        "original requirement", _sample_plan(), [result],
        engineering_context={
            "evidence": [{"kind": "test", "claim": "direct evidence", "excerpt": "12 passed"}],
            "verification": [{"check_type": "targeted", "passed": True, "command_or_check": "npm test"}],
            "requirements": [{"requirement": "login works", "status": "satisfied"}],
            "audit": {"can_complete": True, "summary": "closed"},
        },
    )

    prompt = gateway.chat.call_args.kwargs["messages"][1].content
    assert reviewer.input_mode == "restricted"
    assert "Reviewer 输入模式：restricted" in prompt
    assert "WORKER_SELF_REPORT_SENTINEL" not in prompt
    assert "WORKER_RESPONSE_SENTINEL" not in prompt
    assert result.files_written[0] in prompt
    assert "npm test" in prompt
    assert "direct evidence" in prompt
    assert "login works" in prompt


def test_full_reviewer_mode_can_include_worker_body(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text(
        "reviewer:\n  model: glm-ark\n  input_mode: full\n",
        encoding="utf-8",
    )
    gateway = _mock_gateway('{"passed": true, "issues": [], "final_output": "ok"}')
    result = _sample_results()[0]
    result.content = "FULL_MODE_WORKER_BODY"

    reviewer = Reviewer(gateway, config_path=str(config_path))
    reviewer.review("request", _sample_plan(), [result])

    prompt = gateway.chat.call_args.kwargs["messages"][1].content
    assert reviewer.input_mode == "full"
    assert "Reviewer 输入模式：full" in prompt
    assert "FULL_MODE_WORKER_BODY" in prompt


def test_reviewer_receives_adversarial_findings_as_unexecuted_checks(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    config_path = tmp_path / "workers.yaml"
    config_path.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")
    gateway = _mock_gateway(
        '{"passed": false, "issues": ["counterexample"], "final_output": "blocked"}'
    )

    Reviewer(gateway, config_path=str(config_path)).review(
        "request",
        _sample_plan(),
        _sample_results(),
        engineering_context={
            "audit": {"can_complete": True},
            "adversarial": {
                "status": "refuted",
                "findings": ["exact response differs"],
                "recommended_checks": ["assert lowercase ok"],
            },
        },
    )

    prompt = gateway.chat.call_args.kwargs["messages"][1].content
    assert "status=refuted" in prompt
    assert "exact response differs" in prompt
    assert "assert lowercase ok（未执行）" in prompt
