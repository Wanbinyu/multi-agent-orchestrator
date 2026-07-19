"""Deterministic delivery reports aggregated from complete RunJournal history."""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Literal

import yaml
from pydantic import BaseModel, Field

from src.core.engineering.models import RunJournal, utc_now


ReportScope = Literal["session", "today"]


class DeliveryItem(BaseModel):
    """One deduplicated fact with persistent provenance."""

    label: str
    path: str = ""
    run_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)


class DeliveryReport(BaseModel):
    """Local, model-free report of engineering delivery facts and metrics."""

    scope: ReportScope
    session_id: str = ""
    generated_at: str = Field(default_factory=utc_now)
    run_count: int = 0
    status_counts: dict[str, int] = Field(default_factory=dict)
    created_files: list[DeliveryItem] = Field(default_factory=list)
    modified_files: list[DeliveryItem] = Field(default_factory=list)
    other_changes: list[DeliveryItem] = Field(default_factory=list)
    verification_passed: list[DeliveryItem] = Field(default_factory=list)
    verification_failed: list[DeliveryItem] = Field(default_factory=list)
    pending_checks: list[DeliveryItem] = Field(default_factory=list)
    user_steps: list[DeliveryItem] = Field(default_factory=list)
    residual_risks: list[DeliveryItem] = Field(default_factory=list)
    runs: list[dict[str, Any]] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)

    def to_markdown(self) -> str:
        """Render a compact report without adding claims not present in the model."""
        title = "今日工程报告" if self.scope == "today" else "本会话工程报告"
        lines = [f"# {title}", ""]
        lines.append(
            f"运行 {self.run_count} 轮；完成 {self.status_counts.get('completed', 0)}，"
            f"受阻 {self.status_counts.get('blocked', 0)}，"
            f"失败 {self.status_counts.get('failed', 0)}，"
            f"进行中 {self.status_counts.get('running', 0)}。"
        )
        sections = (
            ("创建", self.created_files),
            ("修改", self.modified_files),
            ("其他变更", self.other_changes),
            ("验证通过", self.verification_passed),
            ("验证失败", self.verification_failed),
            ("待确认", self.pending_checks),
            ("用户步骤", self.user_steps),
            ("残余风险", self.residual_risks),
        )
        for heading, items in sections:
            if not items:
                continue
            lines.extend(["", f"## {heading}"])
            for item in items:
                target = f"：{item.path}" if item.path else ""
                provenance = ", ".join(item.run_ids)
                lines.append(f"- {item.label}{target} (`{provenance}`)")
        if self.runs:
            lines.extend(["", "## 运行记录"])
            for run in self.runs[-20:]:
                lines.append(
                    f"- `{run.get('run_id', '')}` [{run.get('status', '')}] "
                    f"{str(run.get('objective', ''))[:80]}"
                )
            if len(self.runs) > 20:
                lines.append(f"- 其余 {len(self.runs) - 20} 轮已折叠")
        metrics = self.metrics
        lines.extend([
            "",
            "## 指标",
            f"- 输入 token：{metrics.get('input_tokens', 0)}",
            f"- 输出 token：{metrics.get('output_tokens', 0)}",
            f"- 成本：${float(metrics.get('cost_usd', 0.0)):.6f}",
            f"- 有效交付：{metrics.get('effective_deliveries', 0)}",
            f"- 成功率：{float(metrics.get('success_rate', 0.0)):.1%}",
            f"- 首轮可运行率：{float(metrics.get('first_pass_runnable_rate', 0.0)):.1%}",
            f"- 用户返工轮次：{metrics.get('user_rework_runs', 0)}",
            f"- 误诊率：{float(metrics.get('misdiagnosis_rate', 0.0)):.1%}",
            f"- token/有效交付：{float(metrics.get('tokens_per_effective_delivery', 0.0)):.1f}",
        ])
        return "\n".join(lines)


class DeliveryReportBuilder:
    """Aggregate direct RunJournal facts; never asks a model to reconstruct history."""

    def build(
        self,
        journals: Iterable[RunJournal],
        *,
        scope: ReportScope,
        session_id: str = "",
    ) -> DeliveryReport:
        selected = sorted(
            (
                journal
                for journal in journals
                if not session_id or journal.session_id == session_id or scope == "today"
            ),
            key=lambda item: item.started_at,
        )
        report = DeliveryReport(
            scope=scope,
            session_id=session_id if scope == "session" else "",
            run_count=len(selected),
            status_counts=dict(Counter(item.status for item in selected)),
        )
        buckets: dict[str, dict[tuple[str, str], DeliveryItem]] = {
            name: {}
            for name in (
                "created_files", "modified_files", "other_changes",
                "verification_passed", "verification_failed", "pending_checks",
                "user_steps", "residual_risks",
            )
        }
        raw_evidence = 0
        evidence_fingerprints: set[tuple[Any, ...]] = set()
        total_input = 0
        total_output = 0
        total_cost = 0.0
        terminal = 0
        completed = 0
        effective_deliveries = 0
        build_runs = 0
        first_pass_runnable = 0
        rework_runs = 0
        evaluated_hypotheses = 0
        refuted_hypotheses = 0
        role_metrics: dict[tuple[str, str], dict[str, Any]] = {}
        for journal in selected:
            metrics = journal.metrics or {}
            provider_confirmed = (
                "provider_configured" in (metrics.get("confirmed_facts") or [])
            )
            total_input += _int_metric(metrics, "input_tokens")
            total_output += _int_metric(metrics, "output_tokens")
            total_cost += _float_metric(metrics, "cost_usd")
            if journal.status != "running":
                terminal += 1
            if journal.status == "completed":
                completed += 1
            effective = bool(
                journal.status == "completed"
                and journal.audit
                and journal.audit.can_complete
                and (
                    journal.observed_mutation.project_file_count > 0
                    or journal.intent.kind in {"change", "build"}
                )
            )
            effective_deliveries += int(effective)
            is_build = (journal.effective_intent or journal.intent).kind == "build"
            if is_build:
                build_runs += 1
                passed_types = {
                    gate.check_type
                    for gate in journal.verification
                    if gate.passed is True
                }
                required_build_gates = {"targeted", "integration", "full", "smoke"}
                attempts = [
                    int(item.metadata.get("attempts", 1) or 1)
                    for item in journal.evidence
                    if item.source.startswith("worker:")
                ]
                if (
                    journal.status == "completed"
                    and required_build_gates <= passed_types
                    and attempts
                    and max(attempts) == 1
                ):
                    first_pass_runnable += 1
            normalized_objective = journal.objective.casefold()
            if metrics.get("rework") is True or any(
                marker in normalized_objective
                for marker in ("修复", "重试", "补齐", "继续修改", "fix", "retry")
            ):
                rework_runs += 1

            evaluated = [
                item for item in journal.hypotheses if item.status != "untested"
            ]
            evaluated_hypotheses += len(evaluated)
            refuted_hypotheses += sum(item.status == "refuted" for item in evaluated)
            self._collect_roles(role_metrics, metrics.get("collaboration") or {})

            report.runs.append({
                "run_id": journal.run_id,
                "session_id": journal.session_id,
                "objective": journal.objective,
                "status": journal.status,
                "started_at": journal.started_at,
                "audit_status": journal.audit.status if journal.audit else "",
                "can_complete": journal.audit.can_complete if journal.audit else None,
            })

            for evidence in journal.evidence:
                raw_evidence += 1
                evidence_fingerprints.add((
                    evidence.kind, evidence.claim, evidence.path, evidence.command,
                    evidence.success,
                ))
                if evidence.kind == "change" and evidence.success:
                    existed = evidence.metadata.get("file_existed_before")
                    bucket = (
                        "created_files" if existed is False
                        else "modified_files" if existed is True
                        else "other_changes"
                    )
                    self._add(
                        buckets[bucket], evidence.claim, evidence.path,
                        journal.run_id, evidence.id,
                    )
                if evidence.metadata.get("user_step"):
                    self._add(
                        buckets["user_steps"], evidence.claim, evidence.path,
                        journal.run_id, evidence.id,
                    )

            for gate in journal.verification:
                label = f"[{gate.check_type}] {gate.command_or_check or gate.requirement}"
                if gate.passed is True:
                    bucket = "verification_passed"
                elif gate.passed is False:
                    bucket = "verification_failed"
                else:
                    bucket = "pending_checks"
                self._add(buckets[bucket], label, "", journal.run_id, gate.id)
            if journal.audit:
                for missing in journal.audit.missing_checks:
                    self._add(
                        buckets["pending_checks"], missing, "", journal.run_id, ""
                    )
            for requirement in journal.requirements:
                if requirement.status == "unverified":
                    self._add(
                        buckets["pending_checks"], requirement.requirement, "",
                        journal.run_id, requirement.id,
                    )
            for decision in journal.decisions:
                if decision.startswith("[user_step] "):
                    self._add(
                        buckets["user_steps"], decision[12:], "", journal.run_id, ""
                    )
            for risk in journal.residual_risks:
                if provider_confirmed and _contradicts_confirmed_provider(risk):
                    continue
                self._add(
                    buckets["residual_risks"], risk, "", journal.run_id, ""
                )

        for name, values in buckets.items():
            setattr(report, name, list(values.values()))
        total_tokens = total_input + total_output
        report.metrics = {
            "input_tokens": total_input,
            "output_tokens": total_output,
            "cost_usd": round(total_cost, 9),
            "effective_deliveries": effective_deliveries,
            "success_rate": completed / terminal if terminal else 0.0,
            "first_pass_runnable_rate": (
                first_pass_runnable / build_runs if build_runs else 0.0
            ),
            "first_pass_runnable_count": first_pass_runnable,
            "build_runs": build_runs,
            "user_rework_runs": rework_runs,
            "misdiagnosis_rate": (
                refuted_hypotheses / evaluated_hypotheses
                if evaluated_hypotheses else 0.0
            ),
            "refuted_hypotheses": refuted_hypotheses,
            "evaluated_hypotheses": evaluated_hypotheses,
            "tokens_per_effective_delivery": (
                total_tokens / effective_deliveries if effective_deliveries else 0.0
            ),
            "raw_evidence_count": raw_evidence,
            "deduplicated_evidence_count": len(evidence_fingerprints),
            "role_metrics": list(role_metrics.values()),
        }
        return report

    @staticmethod
    def _add(
        bucket: dict[tuple[str, str], DeliveryItem],
        label: str,
        path: str,
        run_id: str,
        evidence_id: str,
    ) -> None:
        key = (label.strip(), path.strip().replace("\\", "/").casefold())
        item = bucket.get(key)
        if item is None:
            item = DeliveryItem(label=label.strip(), path=path.strip())
            bucket[key] = item
        if run_id and run_id not in item.run_ids:
            item.run_ids.append(run_id)
        if evidence_id and evidence_id not in item.evidence_ids:
            item.evidence_ids.append(evidence_id)

    @staticmethod
    def _collect_roles(
        aggregate: dict[tuple[str, str], dict[str, Any]], collaboration: dict[str, Any]
    ) -> None:
        for item in collaboration.get("roles") or []:
            role = str(item.get("role", "unknown"))
            model = str(item.get("actual_model") or item.get("planned_model") or "unknown")
            key = (role, model)
            target = aggregate.setdefault(key, {
                "role": role,
                "model": model,
                "runs": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
            })
            target["runs"] += 1
            target["input_tokens"] += int(item.get("input_tokens", 0) or 0)
            target["output_tokens"] += int(item.get("output_tokens", 0) or 0)
            target["cost_usd"] = round(
                float(target["cost_usd"]) + float(item.get("cost_usd", 0.0) or 0.0),
                9,
            )


def load_today_journals(
    sessions_root: str | Path,
    *,
    local_day: date | None = None,
    limit: int = 1000,
) -> list[RunJournal]:
    """Boundedly load today's journals across sessions, skipping corrupt records."""
    target_day = local_day or datetime.now().astimezone().date()
    journals: dict[str, RunJournal] = {}
    root = Path(sessions_root)
    if not root.is_dir():
        return []
    for path in sorted(root.glob("*/runs/*.yaml"), reverse=True)[: max(1, limit)]:
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            journal = RunJournal(**data)
            started = datetime.fromisoformat(journal.started_at)
            if started.astimezone().date() == target_day:
                journals[journal.run_id] = journal
        except (OSError, ValueError, TypeError, yaml.YAMLError):
            continue
    return sorted(journals.values(), key=lambda item: item.started_at)


def _int_metric(metrics: dict[str, Any], name: str) -> int:
    value = metrics.get(name, 0)
    return int(value) if isinstance(value, (int, float)) else 0


def _float_metric(metrics: dict[str, Any], name: str) -> float:
    value = metrics.get(name, 0.0)
    return float(value) if isinstance(value, (int, float)) else 0.0


def _contradicts_confirmed_provider(risk: str) -> bool:
    normalized = risk.casefold()
    uncertainty = any(marker in normalized for marker in ("可能", "请确认", "也许"))
    provider = any(marker in normalized for marker in ("provider", "模型配置", "未配置", "未开启"))
    return uncertainty and provider
