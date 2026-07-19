"""需求矩阵与确定性完成审计。"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

from src.core.engineering.models import (
    CompletionAudit,
    ObservedMutation,
    RequirementCheck,
    RunJournal,
    RunStatus,
    TaskExecutionPolicy,
    TaskIntent,
    utc_now,
)
from src.core.engineering.verifier import required_checks_for_depth, verification_label


_DEPENDENCY_MANIFESTS = {
    "cargo.toml",
    "composer.json",
    "go.mod",
    "package-lock.json",
    "package.json",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
    "settings.gradle",
    "settings.gradle.kts",
    "yarn.lock",
}


class MutationRiskEscalator:
    """根据真实写入生成审计用 effective intent，不扩大执行权限。"""

    def __init__(self, output_dir: str | Path):
        self.output_dir = Path(output_dir).expanduser().resolve(strict=False)
        self.response_archive = (self.output_dir / "response.md").resolve(strict=False)

    def observe(
        self,
        journal: RunJournal,
        *,
        files_changed: Iterable[str] | None = None,
    ) -> bool:
        before = (
            journal.effective_intent.model_dump() if journal.effective_intent else None,
            journal.observed_mutation.model_dump(),
        )
        observation = ObservedMutation(**journal.observed_mutation.model_dump())
        if observation.original_kind is None:
            observation.original_kind = journal.intent.kind

        project_files = list(observation.project_files)
        ignored_files = list(observation.ignored_files)
        dependency_files = list(observation.dependency_files)
        new_directories = list(observation.new_directories)
        evidence_ids = list(observation.evidence_ids)

        for evidence in journal.evidence:
            if not evidence.success or evidence.metadata.get("skipped", False):
                continue
            candidates: list[str] = []
            if evidence.kind == "change" and evidence.path:
                candidates.append(evidence.path)
            candidates.extend(
                str(path)
                for path in (evidence.metadata.get("files_written") or [])
                if path
            )
            for raw_path in candidates:
                canonical, ignored = self._canonicalize(raw_path)
                if not canonical:
                    continue
                if ignored:
                    self._append_unique(ignored_files, canonical)
                    continue
                self._append_unique(project_files, canonical)
                self._append_unique(evidence_ids, evidence.id)
                if self._is_dependency_manifest(canonical):
                    self._append_unique(dependency_files, canonical)
                if evidence.metadata.get("created_new_directory"):
                    self._append_unique(
                        new_directories, str(Path(canonical).parent)
                    )

        for raw_path in files_changed or []:
            canonical, ignored = self._canonicalize(str(raw_path))
            if not canonical:
                continue
            if ignored:
                self._append_unique(ignored_files, canonical)
                continue
            self._append_unique(project_files, canonical)
            if self._is_dependency_manifest(canonical):
                self._append_unique(dependency_files, canonical)

        observation.project_files = project_files
        observation.ignored_files = ignored_files
        observation.dependency_files = dependency_files
        observation.new_directories = new_directories
        observation.evidence_ids = evidence_ids
        observation.project_file_count = len(project_files)

        if project_files:
            build_risk = (
                journal.intent.kind == "build"
                or len(project_files) >= 2
                or bool(dependency_files)
                or bool(new_directories)
            )
            effective_kind = "build" if build_risk else "change"
            observation.effective_kind = effective_kind
            observation.observed_at = observation.observed_at or utc_now()
            journal.effective_intent = self._effective_intent(
                journal.intent, build=build_risk, file_count=len(project_files)
            )
            decision = (
                f"观察到 {len(project_files)} 个真实项目文件写入，"
                f"完成审计动态提升为 {effective_kind}/"
                f"{journal.effective_intent.risk_level}/"
                f"{journal.effective_intent.policy.verification_depth}；"
                "初始工具权限保持不变。"
            )
            if decision not in journal.decisions:
                journal.decisions.append(decision)
        else:
            observation.effective_kind = None
            journal.effective_intent = None

        journal.observed_mutation = observation
        after = (
            journal.effective_intent.model_dump() if journal.effective_intent else None,
            journal.observed_mutation.model_dump(),
        )
        if before != after:
            journal.updated_at = utc_now()
            return True
        return False

    def _canonicalize(self, raw_path: str) -> tuple[str, bool]:
        value = raw_path.strip()
        if not value:
            return "", False
        path = Path(value).expanduser()
        if path.is_absolute():
            canonical = path.resolve(strict=False)
        else:
            cwd_candidate = (Path.cwd() / path).resolve(strict=False)
            output_candidate = (self.output_dir / path).resolve(strict=False)
            if self._same_path(cwd_candidate, self.response_archive):
                canonical = cwd_candidate
            elif cwd_candidate.exists() and not output_candidate.exists():
                canonical = cwd_candidate
            else:
                canonical = output_candidate
        return str(canonical), self._same_path(canonical, self.response_archive)

    @staticmethod
    def _append_unique(items: list[str], value: str) -> None:
        key = str(value).replace("\\", "/").casefold()
        if all(str(item).replace("\\", "/").casefold() != key for item in items):
            items.append(value)

    @staticmethod
    def _same_path(left: Path, right: Path) -> bool:
        return str(left).replace("\\", "/").casefold() == str(right).replace(
            "\\", "/"
        ).casefold()

    @staticmethod
    def _is_dependency_manifest(path: str) -> bool:
        name = Path(path).name.casefold()
        return name in _DEPENDENCY_MANIFESTS or (
            name.startswith("requirements-") and name.endswith(".txt")
        )

    @staticmethod
    def _effective_intent(
        original: TaskIntent, *, build: bool, file_count: int
    ) -> TaskIntent:
        if build:
            return TaskIntent(
                kind="build",
                scope=list(original.scope),
                risk_level="high",
                write_authorized=True,
                deliverables=["功能实现", "测试", "使用说明"],
                policy=TaskExecutionPolicy(
                    allow_project_writes=True,
                    requires_plan=True,
                    verification_depth="deep",
                    collaboration_allowed=True,
                ),
                classification_source="observed",
                confidence=1.0,
                classification_note=f"观察到 {file_count} 个项目文件或构建风险信号",
            )
        return TaskIntent(
            kind="change",
            scope=list(original.scope),
            risk_level="medium",
            write_authorized=True,
            deliverables=["代码修改", "验证结果"],
            policy=TaskExecutionPolicy(
                allow_project_writes=True,
                requires_plan=False,
                verification_depth="standard",
                collaboration_allowed=True,
            ),
            classification_source="observed",
            confidence=1.0,
            classification_note="观察到 1 个真实项目文件写入",
        )


class CompletionAuditor:
    """用直接证据决定工程任务能否标记 completed。"""

    def audit(self, journal: RunJournal, requested_status: RunStatus) -> CompletionAudit:
        if requested_status != "completed":
            audit = CompletionAudit(
                status="failed" if requested_status == "failed" else "blocked",
                requested_status=requested_status,
                can_complete=False,
                summary=f"运行请求状态为 {requested_status}，不执行完成判定。",
            )
            journal.audit = audit
            return audit

        has_observed_mutation = journal.observed_mutation.project_file_count > 0
        effective_intent = journal.effective_intent or journal.intent
        if not has_observed_mutation and (
            not effective_intent.policy.allow_project_writes
            or not effective_intent.write_authorized
        ):
            journal.requirements = []
            audit = CompletionAudit(
                status="not_required",
                requested_status=requested_status,
                can_complete=True,
                summary="只读或未获写授权的任务不要求工程变更验证门。",
            )
            journal.audit = audit
            return audit

        required_checks = required_checks_for_depth(
            effective_intent.policy.verification_depth
        )
        observed_evidence_ids = set(journal.observed_mutation.evidence_ids)
        change_evidence = [
            item.id
            for item in journal.evidence
            if item.kind == "change"
            and item.success
            and not item.metadata.get("skipped", False)
            and (
                not has_observed_mutation
                or item.id in observed_evidence_ids
            )
        ]
        documentation_evidence = [
            item.id
            for item in journal.evidence
            if item.kind == "change"
            and item.success
            and self._is_documentation_change(item.path, item.metadata)
            and (
                not has_observed_mutation
                or item.id in observed_evidence_ids
            )
        ]
        passed_by_type = {
            item.check_type: item
            for item in journal.verification
            if item.passed is True and item.evidence_ids
        }
        failed_by_type = {
            item.check_type: item
            for item in journal.verification
            if item.passed is False
        }

        requirements = [
            RequirementCheck(
                id="req-implementation",
                requirement=(
                    "功能实现"
                    if "功能实现" in effective_intent.deliverables
                    else "代码修改"
                ),
                implementation_evidence_ids=change_evidence,
                status="satisfied" if change_evidence else "unverified",
                note="必须来自成功的写文件或编辑工具结果。",
            )
        ]
        for check in required_checks:
            gate = passed_by_type.get(check)
            failed_gate = failed_by_type.get(check)
            requirements.append(
                RequirementCheck(
                    id=f"req-verification-{check}",
                    requirement=verification_label(check),
                    verification_gate_ids=[gate.id] if gate else (
                        [failed_gate.id] if failed_gate else []
                    ),
                    status="satisfied" if gate else (
                        "failed" if failed_gate else "unverified"
                    ),
                    note="必须关联真实测试命令产生的 Evidence。",
                )
            )

        if "使用说明" in effective_intent.deliverables:
            requirements.append(
                RequirementCheck(
                    id="req-usage-docs",
                    requirement="使用说明",
                    implementation_evidence_ids=documentation_evidence,
                    status="satisfied" if documentation_evidence else "unverified",
                    note="必须来自 README、docs 或 Markdown 文件的真实写入结果。",
                )
            )

        missing = [] if change_evidence else ["实现证据"]
        missing.extend(
            verification_label(check)
            for check in required_checks
            if check not in passed_by_type and check not in failed_by_type
        )
        failed = [
            verification_label(check)
            for check in required_checks
            if check in failed_by_type and check not in passed_by_type
        ]
        if "使用说明" in effective_intent.deliverables and not documentation_evidence:
            missing.append("使用说明")
        satisfied = [check for check in required_checks if check in passed_by_type]
        can_complete = bool(change_evidence) and not missing and not failed
        audit = CompletionAudit(
            status="passed" if can_complete else "blocked",
            requested_status=requested_status,
            can_complete=can_complete,
            required_checks=required_checks,
            satisfied_checks=satisfied,
            missing_checks=missing,
            failed_checks=failed,
            summary=(
                "实现与风险分级验证均已闭环。"
                if can_complete
                else "缺少完成证据，运行保留但不得标记为已完成。"
            ),
        )
        journal.requirements = requirements
        journal.audit = audit
        return audit

    @staticmethod
    def _is_documentation_change(path: str, metadata: dict) -> bool:
        candidates = [path, *(metadata.get("files_written") or [])]
        for candidate in candidates:
            normalized = str(candidate).replace("\\", "/").casefold()
            name = normalized.rsplit("/", 1)[-1]
            if (
                name.startswith("readme")
                or normalized.endswith(".md")
                or "/docs/" in f"/{normalized.lstrip('/')}"
            ):
                return True
        return False
