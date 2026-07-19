"""把真实测试工具结果转换为风险分级验证门。"""
from __future__ import annotations

import re

from src.core.engineering.evidence import is_test_command
from src.core.engineering.models import (
    RunJournal,
    VerificationCheck,
    VerificationGate,
)
from src.tools.tool_result import ToolResult


_CHECK_LABELS: dict[VerificationCheck, str] = {
    "targeted": "针对性验证",
    "adjacent": "相邻模块回归",
    "integration": "集成测试",
    "full": "全量回归",
    "smoke": "运行时 smoke 验证",
    "external_mock": "外部系统 mock 验证",
    "external_live": "外部系统真实验证",
}


def verification_label(check: VerificationCheck) -> str:
    return _CHECK_LABELS[check]


def required_checks_for_depth(depth: str) -> list[VerificationCheck]:
    mapping: dict[str, list[VerificationCheck]] = {
        "none": [],
        "targeted": ["targeted"],
        "standard": ["targeted", "adjacent"],
        "deep": ["targeted", "integration", "full", "smoke"],
        "continuous": ["external_mock", "external_live"],
    }
    return list(mapping.get(depth, ["targeted"]))


def classify_test_command(command: str) -> VerificationCheck | None:
    if not is_test_command(command):
        return None
    normalized = " ".join(command.strip().lower().split())
    if "smoke" in normalized:
        return "smoke"
    if "integration" in normalized or "e2e" in normalized:
        return "integration"
    if _is_full_suite(normalized):
        return "full"
    return "targeted"


def _is_full_suite(command: str) -> bool:
    if command in {"npm test", "npm run test", "pnpm test", "yarn test"}:
        return True
    match = re.search(r"(?:python\s+-m\s+)?pytest\b(.*)$", command)
    if not match:
        return False
    remainder = match.group(1).strip()
    positional = [part for part in remainder.split() if not part.startswith("-")]
    return not positional


def _has_adjacent_targets(command: str) -> bool:
    targets = re.findall(
        r"(?:tests?[\\/][^\s]+|[^\s\\/]*test[^\s\\/]*\.py)",
        command,
        flags=re.IGNORECASE,
    )
    return len(dict.fromkeys(targets)) >= 2


class VerificationTracker:
    """只接受真实 ToolResult；不从模型正文生成验证结果。"""

    def record(
        self,
        journal: RunJournal,
        tool_name: str,
        params: dict,
        result: ToolResult,
        *,
        cached: bool = False,
        skipped: bool = False,
    ) -> bool:
        if cached or skipped or tool_name not in {"run_command", "frontend_smoke"}:
            return False
        if tool_name == "frontend_smoke":
            evidence_ids = [
                item.id
                for item in journal.evidence
                if item.tool_name == tool_name
            ][-1:]
            return self._add_gate(
                journal,
                "smoke",
                "frontend_smoke",
                result,
                evidence_ids=evidence_ids,
            )
        if (
            result.metadata.get("error_code")
            and result.metadata.get("exit_code") is None
        ):
            return False
        command = str(params.get("command", ""))
        check_type = classify_test_command(command)
        if check_type is None:
            return False
        evidence_ids = [
            item.id
            for item in journal.evidence
            if item.tool_name == tool_name and item.command == command
        ][-1:]
        resolved_cwd = str(result.metadata.get("cwd") or params.get("cwd") or "")
        command_record = (
            f"{command} (cwd: {resolved_cwd})" if resolved_cwd else command
        )
        changed = self._add_gate(
            journal, check_type, command_record, result, evidence_ids=evidence_ids
        )
        if check_type == "targeted" and _has_adjacent_targets(command):
            changed = self._add_gate(
                journal, "adjacent", command_record, result, evidence_ids=evidence_ids
            ) or changed
        return changed

    @staticmethod
    def _add_gate(
        journal: RunJournal,
        check_type: VerificationCheck,
        command: str,
        result: ToolResult,
        *,
        evidence_ids: list[str],
    ) -> bool:
        actual = "\n".join(
            part for part in (result.output.strip(), result.error.strip()) if part
        )
        _, added = journal.add_verification(
            VerificationGate(
                requirement=verification_label(check_type),
                command_or_check=command,
                expected=(
                    "浏览器 smoke 报告通过"
                    if check_type == "smoke" and command == "frontend_smoke"
                    else "命令退出码为 0"
                ),
                actual=actual,
                passed=result.success,
                check_type=check_type,
                evidence_ids=evidence_ids,
            )
        )
        return added
