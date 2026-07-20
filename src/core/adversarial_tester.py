"""Experimental read-only adversarial evidence reviewer."""
from __future__ import annotations

import json
import re

import yaml

from src.core.config_paths import resolve_workers_config_path
from src.gateway.client import GatewayClient
from src.models.schemas import (
    AdversarialTestResult,
    ChatMessage,
    TaskPlan,
    TaskResult,
)


class AdversarialTester:
    """Try to refute implementation claims without tools or project writes."""

    def __init__(
        self,
        gateway: GatewayClient,
        config_path: str = "config/workers.yaml",
        model_override: str | None = None,
        project_rules: str = "",
    ):
        self.gateway = gateway
        with resolve_workers_config_path(config_path).open("r", encoding="utf-8") as stream:
            config = yaml.safe_load(stream) or {}
        adversarial_cfg = config.get("adversarial_tester", {}) or {}
        reviewer_cfg = config.get("reviewer", {}) or {}
        preferred = (
            model_override
            or adversarial_cfg.get("model")
            or reviewer_cfg.get("model")
            or gateway.get_main_model()
            or "glm-ark"
        )
        self.model = gateway.resolve_model(preferred)
        self.system_prompt = adversarial_cfg.get(
            "system_prompt", self._default_system_prompt()
        )
        if project_rules.strip():
            self.system_prompt = f"{self.system_prompt}\n\n{project_rules.strip()}"
        self.last_response = None

    @staticmethod
    def _default_system_prompt() -> str:
        return (
            "你是只读对抗测试工程师。只依据原始需求和直接工具/验证证据，"
            "尝试推翻实现已正确的结论。不得修改文件，不得声称运行了证据中不存在的命令。\n"
            '输出纯 JSON：{"refuted": true/false, "findings": ["..."], '
            '"recommended_checks": ["..."], "summary": "..."}'
        )

    def test(
        self,
        user_request: str,
        plan: TaskPlan,
        results: list[TaskResult],
        engineering_context: dict | None = None,
    ) -> AdversarialTestResult:
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(
                role="user",
                content=self._build_prompt(
                    user_request, plan, results, engineering_context or {}
                ),
            ),
        ]
        response = self.gateway.chat(
            messages=messages,
            model_name=self.model,
            task_id="adversarial-tester",
            max_tokens=2048,
            temperature=0.1,
        )
        self.last_response = response
        try:
            data = self._parse_json(response.content)
        except ValueError:
            return AdversarialTestResult(
                status="inconclusive",
                findings=["对抗测试未返回可解析的结构化 JSON"],
                summary="对抗测试结果不确定",
            )
        return self._validate_result(data)

    @staticmethod
    def _bounded_strings(value: object) -> list[str] | None:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            return None
        return [item.strip()[:500] for item in value[:20] if item.strip()]

    @classmethod
    def _validate_result(cls, data: object) -> AdversarialTestResult:
        if not isinstance(data, dict):
            return AdversarialTestResult(
                status="inconclusive",
                findings=["对抗测试 JSON 顶层不是对象"],
                summary="对抗测试结果不确定",
            )
        refuted = data.get("refuted")
        findings = cls._bounded_strings(data.get("findings", []))
        checks = cls._bounded_strings(data.get("recommended_checks", []))
        summary = data.get("summary", "")
        if (
            not isinstance(refuted, bool)
            or findings is None
            or checks is None
            or not isinstance(summary, str)
            or (refuted and not findings)
        ):
            return AdversarialTestResult(
                status="inconclusive",
                findings=["对抗测试 JSON 字段类型或必填内容无效"],
                summary="对抗测试结果不确定",
            )
        return AdversarialTestResult(
            status="refuted" if refuted else "not_refuted",
            findings=findings,
            recommended_checks=checks,
            summary=summary.strip()[:1000],
        )

    @staticmethod
    def _build_prompt(
        user_request: str,
        plan: TaskPlan,
        results: list[TaskResult],
        engineering_context: dict,
    ) -> str:
        lines = [
            "原始需求：",
            user_request,
            "",
            f"计划摘要：{plan.summary}",
            "",
            "实现职责与直接证据：",
        ]
        for result in results:
            lines.extend([
                f"- task={result.task.id} type={result.task.type} success={result.success}",
                f"  files={', '.join(result.files_written) or '无'}",
                f"  acceptance={'；'.join(result.acceptance_evidence) or '无'}",
            ])
            for call in result.tool_calls:
                if call.get("tool") not in {"run_command", "frontend_smoke"}:
                    continue
                metadata = call.get("metadata") or {}
                lines.append(
                    f"  evidence={call.get('tool')} success={bool(call.get('success'))} "
                    f"command={(call.get('params') or {}).get('command', '')} "
                    f"exit_code={metadata.get('exit_code', '')} "
                    f"output={str(call.get('output', ''))[:300]}"
                )
        lines.append("\n确定性验证门：")
        for gate in engineering_context.get("verification", []) or []:
            lines.append(
                f"- {gate.get('check_type', 'targeted')} passed={gate.get('passed')} "
                f"check={gate.get('command_or_check', '')} actual={str(gate.get('actual', ''))[:300]}"
            )
        audit = engineering_context.get("audit") or {}
        lines.extend([
            "\n完成审计：",
            f"can_complete={bool(audit.get('can_complete', False))}",
            f"missing={audit.get('missing_checks', [])}",
            f"failed={audit.get('failed_checks', [])}",
            "\n请只根据这些直接证据寻找反例或证据缺口。推荐检查不等于已执行验证。",
        ])
        return "\n".join(lines)

    @staticmethod
    def _parse_json(text: str) -> object:
        stripped = text.strip()
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass
        match = re.search(r"```(?:json)?\s*(.*?)```", stripped, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass
        decoder = json.JSONDecoder()
        for match in re.finditer(r"[\[{]", stripped):
            try:
                value, _ = decoder.raw_decode(stripped[match.start() :])
            except json.JSONDecodeError:
                continue
            return value
        raise ValueError("无法从对抗测试输出中解析 JSON")
