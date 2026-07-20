"""Experimental adversarial evidence tester contracts."""
from unittest.mock import MagicMock

from src.core.adversarial_tester import AdversarialTester
from src.models.schemas import ChatResponse, Task, TaskPlan, TaskResult


def _gateway(content: str) -> MagicMock:
    gateway = MagicMock()
    gateway.get_main_model.return_value = "glm-ark"
    gateway.resolve_model.side_effect = lambda model: model
    gateway.chat.return_value = ChatResponse(
        content=content,
        model="glm-ark",
        provider="ark",
        input_tokens=40,
        output_tokens=20,
        cost_usd=0.0001,
    )
    return gateway


def _plan_and_result() -> tuple[TaskPlan, list[TaskResult]]:
    task = Task(
        id="build",
        type="backend_dev",
        title="Build health module",
        input="Create src/main.py",
        assigned_model="glm-ark",
    )
    result = TaskResult(
        task=task,
        success=True,
        content="WORKER_SELF_REPORT_SENTINEL everything is perfect",
        files_written=["src/main.py"],
        acceptance_evidence=["python verify.py passed"],
        tool_calls=[{
            "tool": "run_command",
            "params": {"command": "python verify.py"},
            "success": True,
            "output": "ok",
            "metadata": {"exit_code": 0},
        }],
    )
    return TaskPlan(summary="Build", tasks=[task]), [result]


def test_adversarial_tester_uses_direct_evidence_and_can_refute(tmp_path):
    config = tmp_path / "workers.yaml"
    config.write_text(
        "adversarial_tester:\n  model: glm-ark\n  system_prompt: challenge\n",
        encoding="utf-8",
    )
    gateway = _gateway(
        '{"refuted": true, "findings": ["health returns uppercase OK"], '
        '"recommended_checks": ["assert exact lowercase value"], "summary": "counterexample"}'
    )
    plan, results = _plan_and_result()

    tester = AdversarialTester(gateway, config_path=str(config))
    outcome = tester.test(
        "health must return ok",
        plan,
        results,
        engineering_context={
            "verification": [{
                "check_type": "targeted",
                "passed": True,
                "command_or_check": "python verify.py",
                "actual": "exit 0",
            }],
            "audit": {"can_complete": True},
        },
    )

    assert outcome.status == "refuted"
    assert outcome.findings == ["health returns uppercase OK"]
    prompt = gateway.chat.call_args.kwargs["messages"][1].content
    assert "WORKER_SELF_REPORT_SENTINEL" not in prompt
    assert "python verify.py" in prompt
    assert "exit 0" in prompt
    assert gateway.chat.call_args.kwargs["task_id"] == "adversarial-tester"


def test_adversarial_tester_fails_closed_to_inconclusive(tmp_path):
    config = tmp_path / "workers.yaml"
    config.write_text("reviewer:\n  model: glm-ark\n", encoding="utf-8")
    plan, results = _plan_and_result()

    malformed = AdversarialTester(
        _gateway('{"refuted": true, "findings": [], "summary": 3}'),
        config_path=str(config),
    ).test("request", plan, results)
    plain = AdversarialTester(
        _gateway("not json"), config_path=str(config)
    ).test("request", plan, results)

    assert malformed.status == "inconclusive"
    assert plain.status == "inconclusive"
    assert malformed.findings and plain.findings
