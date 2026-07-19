"""Offline end-to-end stability replay for public engineering fixtures."""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field

from src.core.collaboration import (
    normalize_task_contract,
    validate_collaboration_plan,
)
from src.core.engineering.audit import CompletionAuditor
from src.core.engineering.evidence import ToolEvidenceRecorder
from src.core.engineering.frontend_smoke import (
    BrowserSmokeDriver,
    run_frontend_smoke,
)
from src.core.engineering.journal import RunJournalStore
from src.core.engineering.models import Evidence
from src.core.engineering.report import DeliveryReportBuilder
from src.core.engineering.verifier import VerificationTracker
from src.core.frontend_contract import (
    bind_and_validate_frontend_contract,
    validate_integration_tool_evidence,
    verify_frontend_closure,
)
from src.core.engineering.classifier import TaskIntentClassifier
from src.models.schemas import FrontendBuildContract, Task, TaskPlan
from src.tools.worker_tools import run_command


ReplayMode = Literal["good", "broken_mock", "missing_route"]


class StabilityReplayOutcome(BaseModel):
    fixture_id: str
    mode: ReplayMode
    passed: bool
    run_id: str
    status: str
    stages: dict[str, bool] = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    verification: dict[str, bool | None] = Field(default_factory=dict)
    report_metrics: dict[str, Any] = Field(default_factory=dict)
    provider_calls: int = 0


class StabilityReplayRunner:
    """Replay classification through report generation without a Gateway."""

    def __init__(
        self,
        fixture_dir: str | Path,
        workspace: str | Path,
        *,
        browser_driver: BrowserSmokeDriver | None = None,
    ):
        self.fixture_dir = Path(fixture_dir).resolve()
        self.workspace = Path(workspace).resolve()
        self.browser_driver = browser_driver
        self.evidence_recorder = ToolEvidenceRecorder()
        self.verification_tracker = VerificationTracker()

    def run(self, mode: ReplayMode = "good") -> StabilityReplayOutcome:
        if self.workspace.exists():
            raise ValueError(f"回放工作区已存在：{self.workspace}")
        shutil.copytree(self.fixture_dir / "project", self.workspace)
        if mode == "broken_mock":
            shutil.copyfile(
                self.workspace / "broken-index.html",
                self.workspace / "index.html",
            )
        elif mode == "missing_route":
            (self.workspace / "src" / "pages" / "timeline.js").unlink()

        transcript = self._load_yaml(self.fixture_dir / "transcript.yaml")
        plan = self._load_plan()
        request = str(transcript["request"])
        intent = TaskIntentClassifier().classify(request, "auto")
        store = RunJournalStore(self.workspace / ".mao-replay" / "runs")
        journal = store.create("offline-replay", request, "auto", intent=intent)
        issues: list[str] = []
        expected_intent = transcript.get("expected_intent") or {}
        classification_passed = (
            intent.kind == expected_intent.get("kind")
            and intent.risk_level == expected_intent.get("risk_level")
            and intent.policy.verification_depth
            == expected_intent.get("verification_depth")
        )
        if not classification_passed:
            issues.append("意图分类不符合固定夹具预期")

        plan_passed = True
        try:
            bind_and_validate_frontend_contract(plan)
            validate_collaboration_plan(plan)
        except ValueError as exc:
            plan_passed = False
            issues.append(f"计划合同失败：{exc}")

        for path in sorted(self.workspace.rglob("*")):
            if not path.is_file() or ".mao-replay" in path.parts:
                continue
            relative = path.relative_to(self.workspace)
            journal.add_evidence(Evidence(
                source="fixture:copy",
                claim=f"离线夹具文件已创建：{relative.as_posix()}",
                kind="change",
                path=str(path),
                metadata={"file_existed_before": False},
            ))
        journal.files_changed = [
            item.path for item in journal.evidence if item.kind == "change" and item.path
        ]
        journal.add_evidence(Evidence(
            source="worker:integration",
            claim="离线 integration Worker 完成一次执行",
            kind="runtime",
            metadata={"attempts": 1},
        ))

        closure_issues = verify_frontend_closure(plan.frontend_contract)
        closure_passed = not closure_issues
        issues.extend(closure_issues)
        journal.add_evidence(Evidence(
            source="replay:closure",
            claim=("前端闭包通过" if closure_passed else "前端闭包失败"),
            excerpt="；".join(closure_issues[:10]),
            kind="test",
            success=closure_passed,
        ))

        tool_trace: list[dict[str, Any]] = []
        commands_passed = True
        for command in plan.frontend_contract.verification_commands:
            params = {"command": command, "cwd": str(self.workspace)}
            result = run_command(command, cwd=str(self.workspace), timeout=30)
            commands_passed = commands_passed and result.success
            tool_trace.append(_tool_trace("run_command", params, result))
            self.evidence_recorder.record(journal, "run_command", params, result)
            self.verification_tracker.record(journal, "run_command", params, result)
            if not result.success:
                issues.append(f"验证命令失败：{command}")

        smoke_result = run_frontend_smoke(
            self.workspace,
            plan.frontend_contract.smoke,
            self.workspace / ".mao-replay" / "artifacts",
            browser_driver=self.browser_driver,
        )
        smoke_params = {"project_root": str(self.workspace)}
        tool_trace.append(_tool_trace("frontend_smoke", smoke_params, smoke_result))
        self.evidence_recorder.record(
            journal, "frontend_smoke", smoke_params, smoke_result
        )
        self.verification_tracker.record(
            journal, "frontend_smoke", smoke_params, smoke_result
        )
        if not smoke_result.success:
            issues.append(smoke_result.error or "浏览器 smoke 失败")

        integration_issues = validate_integration_tool_evidence(
            plan.frontend_contract, tool_trace
        )
        integration_passed = not integration_issues
        issues.extend(integration_issues)
        journal.metrics["collaboration"] = {
            "roles": [
                {
                    "role": task.frontend_stage or task.type,
                    "task_id": task.id,
                    "planned_model": task.assigned_model,
                    "actual_model": task.assigned_model,
                    "status": "completed" if integration_passed else "failed",
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost_usd": 0.0,
                }
                for task in plan.tasks
            ],
            "distinct_roles": len({task.frontend_stage for task in plan.tasks}),
            "distinct_models": len({task.assigned_model for task in plan.tasks}),
        }
        journal.metrics.update({
            "input_tokens": 0,
            "output_tokens": 0,
            "cost_usd": 0.0,
            "offline_replay": True,
            "fixture_id": str(transcript["fixture_id"]),
            "provider_calls": 0,
        })
        audit = CompletionAuditor().audit(journal, "completed")
        deterministic_gates_passed = all((
            classification_passed,
            plan_passed,
            closure_passed,
            commands_passed,
            smoke_result.success,
            integration_passed,
        ))
        status = (
            "completed"
            if audit.can_complete and deterministic_gates_passed
            else "blocked"
        )
        residual_risks = (
            []
            if deterministic_gates_passed
            else ["离线稳定性回放存在未通过的确定性前置门。"]
        )
        journal.finish(status, residual_risks=residual_risks)
        store.save(journal)
        delivery_report = DeliveryReportBuilder().build(
            [journal], scope="session", session_id=journal.session_id
        )
        stages = {
            "classification": classification_passed,
            "plan_contract": plan_passed,
            "closure": closure_passed,
            "commands": commands_passed,
            "browser_smoke": smoke_result.success,
            "integration_evidence": integration_passed,
            "completion_audit": audit.can_complete,
            "delivery_report": delivery_report.run_count == 1,
        }
        passed = all(stages.values())
        return StabilityReplayOutcome(
            fixture_id=str(transcript["fixture_id"]),
            mode=mode,
            passed=passed,
            run_id=journal.run_id,
            status=status,
            stages=stages,
            issues=list(dict.fromkeys(issue for issue in issues if issue)),
            verification={
                gate.check_type: gate.passed for gate in journal.verification
            },
            report_metrics=delivery_report.metrics,
            provider_calls=0,
        )

    def _load_plan(self) -> TaskPlan:
        raw = self._load_yaml(self.fixture_dir / "plan.yaml")
        replaced = _replace_project_root(raw, str(self.workspace))
        tasks = [
            normalize_task_contract(Task(**task))
            for task in replaced.get("tasks", [])
        ]
        return TaskPlan(
            summary=str(replaced.get("summary", "")),
            tasks=tasks,
            frontend_contract=FrontendBuildContract(
                **replaced["frontend_contract"]
            ),
        )

    @staticmethod
    def _load_yaml(path: Path) -> dict[str, Any]:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"夹具必须是映射：{path.name}")
        return data


def _replace_project_root(value: Any, project_root: str) -> Any:
    if isinstance(value, str):
        return value.replace("{{PROJECT_ROOT}}", project_root.replace("\\", "/"))
    if isinstance(value, list):
        return [_replace_project_root(item, project_root) for item in value]
    if isinstance(value, dict):
        return {
            key: _replace_project_root(item, project_root)
            for key, item in value.items()
        }
    return value


def _tool_trace(tool: str, params: dict[str, Any], result: Any) -> dict[str, Any]:
    return {
        "tool": tool,
        "params": params,
        "success": result.success,
        "output": result.output,
        "error": result.error,
        "metadata": result.metadata,
    }
