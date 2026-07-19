"""Read-only multi-model refinement for persistent Plan mode."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from src.core.config_paths import resolve_workers_config_path
from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage


@dataclass
class PlanningCouncilResult:
    content: str
    roles: list[dict[str, str]] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "roles": list(self.roles),
            "diagnostics": list(self.diagnostics),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cost_usd": self.cost_usd,
        }


class PlanningCouncil:
    """Use configured role models to challenge a draft without executing tools."""

    def __init__(
        self,
        gateway: GatewayClient,
        *,
        config_path: str = "config/workers.yaml",
        project_rules: str = "",
        permission_context: dict[str, Any] | None = None,
    ) -> None:
        self.gateway = gateway
        self.config = self._load_config(config_path)
        self.project_rules = project_rules[:8_000]
        self.permission_context = permission_context or {}

    @staticmethod
    def _load_config(path: str) -> dict[str, Any]:
        try:
            with resolve_workers_config_path(path).open("r", encoding="utf-8") as stream:
                data = yaml.safe_load(stream) or {}
                return data if isinstance(data, dict) else {}
        except (OSError, yaml.YAMLError):
            return {}

    def refine(self, objective: str, draft: str, evidence: str = "") -> PlanningCouncilResult:
        result = PlanningCouncilResult(content=draft)
        if not draft.strip():
            result.diagnostics.append("主模型未提供可评议的 Plan 草案")
            return result

        shared = self._shared_context(objective, draft, evidence)
        recon = self._call_role(
            result,
            "reconnaissance",
            self._role_model("continuity_checker"),
            "你是只读证据检查员。只根据提供的证据和草案列出已确认约束、证据缺口、未知项；禁止假设已修改文件或已运行测试。",
            shared,
        )
        architect = self._call_role(
            result,
            "architect",
            self._role_model("architect", section="orchestrator"),
            "你是架构规划员。基于需求、草案和证据检查结果，给出有边界、可按步骤实施且可验收的方案；不要执行或声称已执行。",
            f"{shared}\n\n【证据检查】\n{recon}",
        )
        critic = self._call_role(
            result,
            "critic",
            self._role_model("editor", section="reviewer"),
            "你是计划审查员。挑战方案中的越权风险、遗漏、错误依赖、回滚缺口和测试不足，按严重度列出必须修正项。禁止执行工具。",
            f"{shared}\n\n【架构方案】\n{architect}",
        )
        synthesis = self._call_role(
            result,
            "synthesizer",
            self.gateway.get_main_model(),
            (
                "你是最终计划负责人。综合草案、证据检查、架构方案和审查意见，输出一份唯一的最终实施计划。"
                "必须包含范围与非目标、证据与未知项、分步实施、权限边界、验证与验收、风险与回滚。"
                "只输出方案，不执行工具，不声称已完成。"
            ),
            (
                f"{shared}\n\n【证据检查】\n{recon}\n\n【架构方案】\n{architect}"
                f"\n\n【审查意见】\n{critic}"
            ),
        )
        if synthesis.strip():
            result.content = synthesis.strip()
        return result

    def _shared_context(self, objective: str, draft: str, evidence: str) -> str:
        permission = json.dumps(self.permission_context, ensure_ascii=False, default=str)[:4_000]
        return (
            f"【用户目标】\n{objective[:8_000]}\n\n"
            f"【主 Agent 只读草案】\n{draft[:12_000]}\n\n"
            f"【真实工具证据摘要】\n{evidence[:8_000] or '无；所有未验证细节必须标记为待确认'}\n\n"
            f"【项目规则】\n{self.project_rules or '无'}\n\n"
            f"【权限规则摘要】\n{permission or '{}'}\n\n"
            "全程处于 Plan 模式：没有任何写入、命令、MCP 写操作或 Worker 执行权限。"
        )

    def _role_model(self, worker_name: str, *, section: str = "") -> str | None:
        workers = self.config.get("available_workers", {})
        worker = workers.get(worker_name, {}) if isinstance(workers, dict) else {}
        preferred = worker.get("default_model") if isinstance(worker, dict) else None
        if not preferred and section:
            section_cfg = self.config.get(section, {})
            preferred = section_cfg.get("model") if isinstance(section_cfg, dict) else None
        return preferred or self.gateway.get_main_model()

    def _call_role(
        self,
        result: PlanningCouncilResult,
        role: str,
        preferred_model: str | None,
        system_prompt: str,
        user_content: str,
    ) -> str:
        try:
            model = self.gateway.resolve_model(preferred_model)
            response = self.gateway.chat(
                messages=[
                    ChatMessage(role="system", content=system_prompt),
                    ChatMessage(role="user", content=user_content),
                ],
                model_name=model,
                task_id=f"plan-{role}",
                max_tokens=4096,
                temperature=0.2,
            )
            content = response.content if isinstance(response.content, str) else ""
            if not content.strip():
                raise ValueError("模型返回空内容")
            result.roles.append({"role": role, "model": str(model), "status": "completed"})
            result.input_tokens += int(response.input_tokens or 0)
            result.output_tokens += int(response.output_tokens or 0)
            result.cost_usd += float(response.cost_usd or 0.0)
            return content.strip()
        except Exception as exc:  # one advisory role must not destroy the draft
            result.roles.append({"role": role, "model": str(preferred_model or ""), "status": "failed"})
            result.diagnostics.append(f"{role} 角色失败：{exc}")
            return ""
