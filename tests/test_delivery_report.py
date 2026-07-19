"""Deterministic cross-RunJournal delivery report tests."""
from __future__ import annotations

from src.core.engineering import (
    CompletionAudit,
    DeliveryReportBuilder,
    Evidence,
    Hypothesis,
    RunJournalStore,
    TaskIntentClassifier,
    VerificationGate,
    load_today_journals,
)


def _build_report_journals(tmp_path):
    store = RunJournalStore(tmp_path / "sessions" / "s1" / "runs")
    build_request = "我现在接了一个智慧矿区的项目，现在给我做一个纯前端的项目"
    build_intent = TaskIntentClassifier().classify(build_request, "auto")
    build = store.create("s1", build_request, "auto", intent=build_intent)
    created, _ = build.add_evidence(Evidence(
        source="tool:write_file",
        claim="已修改文件：src/app.tsx",
        kind="change",
        path="src/app.tsx",
        metadata={"file_existed_before": False},
    ))
    build.add_evidence(Evidence(
        source="worker:integration",
        claim="Worker integration 执行成功",
        kind="runtime",
        metadata={"attempts": 1},
    ))
    build.add_verification(VerificationGate(
        requirement="针对性", command_or_check="npm run test:targeted", passed=True,
        check_type="targeted", evidence_ids=[created.id],
    ))
    build.add_verification(VerificationGate(
        requirement="构建", command_or_check="npm run build", passed=True,
        check_type="integration", evidence_ids=[created.id],
    ))
    build.add_verification(VerificationGate(
        requirement="全量", command_or_check="npm test", passed=True,
        check_type="full", evidence_ids=[created.id],
    ))
    build.add_verification(VerificationGate(
        requirement="运行时 smoke", command_or_check="frontend_smoke", passed=True,
        check_type="smoke", evidence_ids=[created.id],
    ))
    build.observed_mutation.project_file_count = 1
    build.audit = CompletionAudit(status="passed", can_complete=True, summary="闭环")
    build.hypotheses.append(Hypothesis(
        statement="API 未配置", status="refuted",
        contradicting_evidence_ids=[created.id],
    ))
    build.finish("completed", metrics={
        "input_tokens": 100,
        "output_tokens": 40,
        "cost_usd": 0.02,
        "confirmed_facts": ["provider_configured"],
        "collaboration": {"roles": [{
            "role": "pages", "actual_model": "kimi", "planned_model": "kimi",
            "input_tokens": 60, "output_tokens": 20, "cost_usd": 0.01,
        }]},
    })
    store.save(build)

    repair_intent = TaskIntentClassifier().classify("修复登录并重试", "auto")
    repair = store.create("s1", "修复登录并重试", "auto", intent=repair_intent)
    repair.add_evidence(Evidence(
        source="tool:edit_file",
        claim="已修改文件：src/app.tsx",
        kind="change",
        path="src/app.tsx",
        metadata={"file_existed_before": True},
    ))
    repair.add_evidence(Evidence(
        source="tool:write_file",
        claim="已修改文件：src/app.tsx",
        kind="change",
        path="src/app.tsx",
        metadata={"file_existed_before": False},
    ))
    repair.add_verification(VerificationGate(
        requirement="运行时 smoke", command_or_check="frontend_smoke", passed=False,
        check_type="smoke",
    ))
    repair.audit = CompletionAudit(
        status="blocked", can_complete=False, summary="未闭环",
        missing_checks=["全量回归"], failed_checks=["运行时 smoke 验证"],
    )
    repair.decisions.append("[user_step] 用户需要在测试环境确认摄像头权限")
    repair.residual_risks = [
        "Provider 可能未配置，请确认", "摄像头权限仍待确认",
    ]
    repair.finish("blocked", metrics={
        "input_tokens": 50, "output_tokens": 10, "cost_usd": 0.005,
        "rework": True,
        "confirmed_facts": ["provider_configured"],
        "collaboration": {"roles": [{
            "role": "pages", "actual_model": "kimi", "planned_model": "kimi",
            "input_tokens": 30, "output_tokens": 5, "cost_usd": 0.003,
        }]},
    })
    store.save(repair)
    return store, build, repair


def test_report_aggregates_all_runs_with_provenance_and_truthful_metrics(tmp_path):
    store, build, repair = _build_report_journals(tmp_path)

    report = DeliveryReportBuilder().build(
        store.list(), scope="session", session_id="s1"
    )

    assert report.run_count == 2
    assert report.status_counts == {"completed": 1, "blocked": 1}
    assert len(report.created_files) == 1
    assert report.created_files[0].run_ids == [build.run_id, repair.run_id]
    assert report.modified_files[0].path == "src/app.tsx"
    assert report.verification_passed
    assert report.verification_failed[0].run_ids == [repair.run_id]
    assert {item.label for item in report.pending_checks} >= {"全量回归"}
    assert report.user_steps[0].label.startswith("用户需要")
    assert [item.label for item in report.residual_risks] == ["摄像头权限仍待确认"]
    assert report.metrics["input_tokens"] == 150
    assert report.metrics["output_tokens"] == 50
    assert report.metrics["cost_usd"] == 0.025
    assert report.metrics["effective_deliveries"] == 1
    assert report.metrics["success_rate"] == 0.5
    assert report.metrics["first_pass_runnable_rate"] == 1.0
    assert report.metrics["user_rework_runs"] == 1
    assert report.metrics["misdiagnosis_rate"] == 1.0
    assert report.metrics["tokens_per_effective_delivery"] == 200
    assert report.metrics["raw_evidence_count"] > report.metrics["deduplicated_evidence_count"]
    assert report.metrics["role_metrics"] == [{
        "role": "pages", "model": "kimi", "runs": 2,
        "input_tokens": 90, "output_tokens": 25, "cost_usd": 0.013,
    }]

    markdown = report.to_markdown()
    assert build.run_id in markdown and repair.run_id in markdown
    assert "Provider 可能未配置" not in markdown
    assert "token/有效交付：200.0" in markdown


def test_today_loader_scans_all_sessions_and_skips_corrupt_journal(tmp_path):
    _store, build, _repair = _build_report_journals(tmp_path)
    second = RunJournalStore(tmp_path / "sessions" / "s2" / "runs")
    other = second.create("s2", "检查另一个项目", "auto")
    other.finish("completed")
    second.save(other)
    corrupt = tmp_path / "sessions" / "s3" / "runs" / "bad.yaml"
    corrupt.parent.mkdir(parents=True)
    corrupt.write_text("not: [valid", encoding="utf-8")

    journals = load_today_journals(tmp_path / "sessions")

    assert {item.run_id for item in journals} >= {build.run_id, other.run_id}
    report = DeliveryReportBuilder().build(journals, scope="today")
    assert report.run_count == 3
    assert {item["session_id"] for item in report.runs} == {"s1", "s2"}


def test_today_report_does_not_apply_provider_fact_across_sessions(tmp_path):
    configured = RunJournalStore(tmp_path / "sessions" / "configured" / "runs")
    first = configured.create("configured", "configured provider", "auto")
    first.finish("completed", metrics={"confirmed_facts": ["provider_configured"]})
    configured.save(first)

    unconfigured = RunJournalStore(tmp_path / "sessions" / "unconfigured" / "runs")
    second = unconfigured.create("unconfigured", "check provider", "auto")
    second.residual_risks = ["Provider 可能未配置，请确认"]
    second.finish("blocked")
    unconfigured.save(second)

    report = DeliveryReportBuilder().build(
        [first, second], scope="today"
    )

    assert [item.label for item in report.residual_risks] == [
        "Provider 可能未配置，请确认"
    ]
