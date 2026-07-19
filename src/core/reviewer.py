"""审查工程师 Reviewer"""
from __future__ import annotations

import json
import re
from typing import Literal

import yaml

from src.core.config_paths import resolve_workers_config_path
from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, ReviewResult, TaskPlan, TaskResult


ReviewInputMode = Literal["restricted", "full"]


class Reviewer:
    """汇总 Worker 执行结果，进行审查并输出最终整合内容"""

    def __init__(
        self,
        gateway: GatewayClient,
        config_path: str = "config/workers.yaml",
        model_override: str | None = None,
        project_rules: str = "",
        input_mode: ReviewInputMode | None = None,
    ):
        self.gateway = gateway
        self.config = self._load_config(config_path)
        reviewer_cfg = self.config.get("reviewer", {})
        configured_mode = input_mode or reviewer_cfg.get("input_mode", "restricted")
        self.input_mode: ReviewInputMode = (
            configured_mode if configured_mode in {"restricted", "full"} else "restricted"
        )
        preferred = (
            model_override
            or reviewer_cfg.get("model")
            or gateway.get_main_model()
            or "glm-ark"
        )
        self.model = gateway.resolve_model(preferred)
        self.system_prompt = reviewer_cfg.get("system_prompt", self._default_system_prompt())
        if project_rules.strip():
            self.system_prompt = f"{self.system_prompt}\n\n{project_rules.strip()}"
        self.last_response = None

    def _load_config(self, path: str) -> dict:
        with resolve_workers_config_path(path).open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def _default_system_prompt(self) -> str:
        return (
            "你是审查工程师。你会收到多个子任务的执行结果。\n"
            "请检查：\n"
            "1. 各模块结果是否一致；\n"
            "2. 是否满足原始需求；\n"
            "3. 是否存在明显错误。\n"
            '输出格式：{"passed": true/false, "issues": ["..."], "final_output": "整合后的最终内容"}'
        )

    def review(
        self,
        user_request: str,
        plan: TaskPlan,
        results: list[TaskResult],
        engineering_context: dict | None = None,
    ) -> ReviewResult:
        """执行审查"""
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(
                role="user",
                content=self._build_review_prompt(
                    user_request, plan, results, engineering_context
                ),
            ),
        ]

        response = self.gateway.chat(
            messages=messages,
            model_name=self.model,
            task_id="reviewer",
            max_tokens=4096,
            temperature=0.2,
        )
        self.last_response = response

        try:
            review_data = self._parse_json(response.content)
        except ValueError:
            return self._enforce_engineering_audit(
                ReviewResult(
                    passed=False,
                    issues=["Reviewer 未返回可解析的结构化 JSON，不能自动通过"],
                    final_output=str(response.content),
                ),
                engineering_context,
            )

        # 兼容模型只返回文本的情况：构造一个默认 ReviewResult
        if not isinstance(review_data, dict):
            return self._enforce_engineering_audit(
                ReviewResult(
                    passed=False,
                    issues=["Reviewer 返回格式无效，不能自动通过"],
                    final_output=str(response.content),
                ),
                engineering_context,
            )

        passed = review_data.get("passed", False)
        issues = review_data.get("issues", [])
        final_output = review_data.get("final_output", "")
        if (
            not isinstance(passed, bool)
            or not isinstance(issues, list)
            or any(not isinstance(item, str) for item in issues)
            or not isinstance(final_output, str)
        ):
            return self._enforce_engineering_audit(
                ReviewResult(
                    passed=False,
                    issues=["Reviewer JSON 字段类型无效，不能自动通过"],
                    final_output=str(response.content),
                ),
                engineering_context,
            )
        reviewed = self._enforce_engineering_audit(
            ReviewResult(
                passed=passed,
                issues=issues,
                final_output=final_output,
            ),
            engineering_context,
        )
        failed_tasks = [result.task.id for result in results if not result.success]
        if not failed_tasks:
            return reviewed
        return ReviewResult(
            passed=False,
            issues=list(dict.fromkeys([
                *reviewed.issues,
                "存在失败的确定性子任务：" + "、".join(failed_tasks),
            ])),
            final_output=reviewed.final_output,
        )

    def _build_review_prompt(
        self,
        user_request: str,
        plan: TaskPlan,
        results: list[TaskResult],
        engineering_context: dict | None = None,
    ) -> str:
        lines = [
            f"Reviewer 输入模式：{self.input_mode}",
            (
                "受限模式仅依据计划与直接证据，Worker 输出正文已排除。"
                if self.input_mode == "restricted"
                else "完整模式包含 Worker 输出正文。"
            ),
            "",
            "原始需求：",
            user_request,
            "",
            f"任务总览：{plan.summary}",
            "",
            "子任务执行结果：",
        ]

        if plan.frontend_contract is not None:
            lines.extend([
                "前端构建合同：",
                json.dumps(
                    plan.frontend_contract.model_dump(),
                    ensure_ascii=False,
                    indent=2,
                ),
                "",
            ])

        for result in results:
            lines.append(f"\n--- [{result.task.id}] {result.task.title} ---")
            lines.append(f"类型：{result.task.type}")
            lines.append(f"职责阶段：{result.task.frontend_stage or '通用'}")
            lines.append(f"计划模型：{result.task.assigned_model}")
            if result.response is not None:
                lines.append(f"实际模型：{result.response.model}")
            lines.append(f"状态：{'成功' if result.success else '失败'}")
            if not result.success:
                lines.append(f"错误：{result.error}")
            lines.append(f"输出文件：{', '.join(result.files_written) or '无'}")
            lines.append(
                "验收证据："
                + ("；".join(result.acceptance_evidence) or "无")
            )
            command_evidence = [
                call
                for call in result.tool_calls
                if call.get("tool") == "run_command"
            ]
            lines.append("真实命令证据：")
            if not command_evidence:
                lines.append("- 无")
            for call in command_evidence:
                metadata = call.get("metadata") or {}
                lines.append(
                    f"- success={bool(call.get('success'))} | "
                    f"command={(call.get('params') or {}).get('command', '')} | "
                    f"cwd={metadata.get('cwd', '')} | "
                    f"exit_code={metadata.get('exit_code', '')} | "
                    f"output={str(call.get('output', ''))[:300]}"
                )
            if result.success and self.input_mode == "full":
                lines.append("输出内容：")
                lines.append(result.content)

        if engineering_context:
            audit = engineering_context.get("audit") or {}
            lines.extend(["", "确定性工程审计："])
            lines.append(f"可完成：{bool(audit.get('can_complete', False))}")
            lines.append(f"摘要：{audit.get('summary', '')}")
            lines.append(
                "缺失检查：" + "、".join(audit.get("missing_checks", []) or ["无"])
            )
            lines.append(
                "失败检查：" + "、".join(audit.get("failed_checks", []) or ["无"])
            )
            lines.append("证据摘要：")
            for evidence in (engineering_context.get("evidence") or [])[-20:]:
                lines.append(
                    f"- [{evidence.get('kind', 'unknown')}] "
                    f"{evidence.get('claim', '')} | "
                    f"{str(evidence.get('excerpt', ''))[:300]}"
                )
            lines.append("验证门：")
            for gate in engineering_context.get("verification") or []:
                lines.append(
                    f"- {gate.get('check_type', 'targeted')} | "
                    f"passed={gate.get('passed')} | {gate.get('command_or_check', '')}"
                )
            lines.append("需求核对：")
            for requirement in engineering_context.get("requirements") or []:
                lines.append(
                    f"- status={requirement.get('status', 'unverified')} | "
                    f"{requirement.get('requirement', '')}"
                )

        lines.append("\n请根据以上结果进行审查，按指定 JSON 格式输出。")
        return "\n".join(lines)

    @staticmethod
    def _enforce_engineering_audit(
        result: ReviewResult,
        engineering_context: dict | None,
    ) -> ReviewResult:
        if not engineering_context:
            return result
        audit = engineering_context.get("audit") or {}
        if audit.get("can_complete", False):
            return result
        details = [
            *(audit.get("missing_checks") or []),
            *(audit.get("failed_checks") or []),
        ]
        issue = "确定性工程审计未通过"
        if details:
            issue += f"：{'、'.join(dict.fromkeys(details))}"
        issues = list(dict.fromkeys([*result.issues, issue]))
        return ReviewResult(
            passed=False,
            issues=issues,
            final_output=result.final_output,
        )

    def _parse_json(self, text: str) -> dict:
        """从文本中提取 JSON"""
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试从 ```json 代码块中提取
        pattern = r"```(?:json)?\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # 尝试从第一个 { 到最后一个 } 提取
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass

        raise ValueError(f"无法从模型输出中解析 JSON:\n{text}")
