"""需求矩阵与确定性完成审计。"""
from __future__ import annotations

from src.core.engineering.models import (
    CompletionAudit,
    RequirementCheck,
    RunJournal,
    RunStatus,
)
from src.core.engineering.verifier import required_checks_for_depth, verification_label


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

        if (
            not journal.intent.policy.allow_project_writes
            or not journal.intent.write_authorized
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
            journal.intent.policy.verification_depth
        )
        change_evidence = [
            item.id
            for item in journal.evidence
            if item.kind == "change"
            and item.success
            and not item.metadata.get("skipped", False)
        ]
        documentation_evidence = [
            item.id
            for item in journal.evidence
            if item.kind == "change"
            and item.success
            and self._is_documentation_change(item.path, item.metadata)
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
                    if "功能实现" in journal.intent.deliverables
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

        if "使用说明" in journal.intent.deliverables:
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
        if "使用说明" in journal.intent.deliverables and not documentation_evidence:
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
