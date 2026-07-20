"""总工 Orchestrator"""
from __future__ import annotations

import json
import re

import yaml

from src.gateway.client import GatewayClient
from src.core.collaboration import normalize_task_contract, validate_collaboration_plan
from src.core.config_paths import resolve_workers_config_path
from src.core.frontend_contract import (
    bind_and_validate_frontend_contract,
    is_high_risk_frontend_request,
)
from src.models.schemas import ChatMessage, FrontendBuildContract, Task, TaskPlan


# 场景特定的任务拆分指导，会追加到 orchestrator system_prompt 后面
SCENARIO_INSTRUCTIONS: dict[str, str] = {
    "novel": """
【小说创作任务编排规则】
1. 必须先生成大纲任务（plot_designer），再生成正文创作任务（writer）。
2. 正文章节必须顺序创作：第二章依赖第一章，第三章依赖第二章，以此类推。
3. 每个 writer 任务的 input 中可以使用 {{前置任务id.output}} 引用前置章节/大纲内容。
4. 一致性检查（continuity_checker）和润色（editor）必须依赖所有 writer 任务完成后执行。
5. 必须在每个任务的 depends_on 字段中正确填写依赖的任务 id。
""",
    "software": """
【软件开发任务编排规则】
1. 必须先生成架构/接口文档任务（architect），明确系统结构、API 接口、数据模型。
2. 前端开发（frontend_dev）和后端开发（backend_dev）可以并行执行，但必须依赖 architect 任务。
3. 每个实现任务的 input 中可以使用 {{architect_task_id.output}} 引用架构文档内容。
4. 测试/集成任务（tester）必须依赖 frontend_dev 和 backend_dev 完成后执行。
5. 必须在每个任务的 depends_on 字段中正确填写依赖的任务 id。
6. 每个写任务必须声明 execution_mode=write；测试任务声明 verify；只读调查声明 read。
7. 相对路径默认写入隔离任务目录；只有确需修改共享项目时才填写 owned_paths 绝对路径，且并行任务不得重叠。
8. 对不能安全并行的迁移、集成和共享配置任务设置 parallel_safe=false。
""",
}

HIGH_RISK_FRONTEND_INSTRUCTION = """
【高风险前端多模型构建合同】
这是项目级前端构建，必须输出 frontend_contract，并固定拆成四个 Worker 阶段：
1. architecture_scaffold：architect，负责架构、脚手架、入口、路由和依赖清单。
2. pages：frontend_dev，负责所有页面与页面级组件，依赖 architecture_scaffold。
3. data_api：frontend_dev，负责数据模型、Mock/真实 API 和状态层，依赖 architecture_scaffold。
4. integration：tester，execution_mode=verify，直接依赖以上全部实现任务，最后执行。
Reviewer 是系统内置第五职责，不要把 Reviewer 伪造成子任务。
每个任务填写 frontend_stage。frontend_contract 必须包含 project_root、entrypoints、routes(path/target)、dependencies、ownership、verification_commands、smoke_paths 和 smoke。
ownership 必须逐任务精确等于 owned_paths；并行 pages 与 data_api 不得拥有重叠路径。smoke_paths 必须都在 routes 中。
smoke.start_command 使用 argv 数组且必须包含 {port}，routes 为每个 smoke_path 声明 visible/text/table_rows/canvas_nonblank/not_visible 断言；可选 login 和 layout_pairs。
integration 会确定性检查入口、路由目标、相对 import、package.json 依赖，并要求每条 verification_commands 都有真实成功的 run_command 证据及成功的 frontend_smoke 证据；Worker 自述不能代替工具证据。
在可用模型允许时，为不同职责选择至少两个合适模型；模型不可用时保持职责分离并使用已配置回退。
"""


WORKER_TYPE_ALIASES: dict[str, str] = {
    "code_writer": "backend_dev",
    "coder": "backend_dev",
    "developer": "backend_dev",
    "implementer": "backend_dev",
    "backend": "backend_dev",
    "frontend": "frontend_dev",
    "qa": "tester",
    "test": "tester",
    "verifier": "tester",
}

SOFTWARE_WORKER_TYPE_ALIASES: dict[str, str] = {
    "plot_designer": "architect",
    "writer": "backend_dev",
    "editor": "tester",
    "continuity_checker": "tester",
}


def _normalize_task_text_fields(raw_task: object) -> dict:
    """Normalize common LLM list output for free-form task text fields only."""
    if not isinstance(raw_task, dict):
        raise ValueError("模型输出的 tasks 条目必须是对象")
    normalized = dict(raw_task)
    for field in ("output_format", "acceptance"):
        value = normalized.get(field)
        if isinstance(value, list):
            normalized[field] = "\n".join(
                item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                for item in value
            )
    return normalized


def _detect_scenario(user_request: str) -> str:
    """根据用户需求关键词检测场景类型"""
    text = user_request.lower()
    novel_keywords = ["小说", "故事", "章节", "人物", "剧情", "大纲", "仙侠", "玄幻", "言情", "虐恋", "吸血鬼"]
    software_keywords = [
        "开发", "系统", "功能", "前端", "后端", "api", "接口", "页面", "网站", "app",
        "登录", "注册", "程序", "代码", "软件", "脚本", "python", "java", "javascript",
        "js", "ts", "typescript", "html", "css", "sql", "react", "vue", "fastapi",
        "flask", "django", "spring", "node", "实现", "搭建", "构建", "部署",
    ]

    novel_score = sum(1 for kw in novel_keywords if kw in text)
    software_score = sum(1 for kw in software_keywords if kw in text)

    if novel_score > software_score:
        return "novel"
    if software_score > novel_score:
        return "software"
    return "novel"


class Orchestrator:
    """需求分析与任务拆分"""

    def __init__(
        self,
        gateway: GatewayClient,
        config_path: str = "config/workers.yaml",
        model_override: str | None = None,
        project_rules: str = "",
    ):
        self.gateway = gateway
        self.config = self._load_config(config_path)
        preferred = (
            model_override
            or self.config.get("orchestrator", {}).get("model")
            or gateway.get_main_model()
            or "claude-fable-5"
        )
        self.model = gateway.resolve_model(preferred)
        self.system_prompt = self.config.get("orchestrator", {}).get("system_prompt", "")
        self.project_rules = project_rules.strip()
        self.last_response = None

    def _load_config(self, path: str) -> dict:
        with resolve_workers_config_path(path).open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def plan(self, user_request: str, memory_context: str | None = None) -> TaskPlan:
        """将用户需求拆分为任务计划"""
        scenario = _detect_scenario(user_request)
        scenario_instruction = SCENARIO_INSTRUCTIONS.get(scenario, "")
        system_prompt = f"{self.system_prompt}\n{scenario_instruction}".strip()
        high_risk_frontend = is_high_risk_frontend_request(user_request)
        if high_risk_frontend:
            system_prompt = f"{system_prompt}\n{HIGH_RISK_FRONTEND_INSTRUCTION}".strip()
        if memory_context:
            system_prompt = f"{system_prompt}\n\n{memory_context}".strip()
        if self.project_rules:
            system_prompt = f"{system_prompt}\n\n{self.project_rules}".strip()

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=f"用户需求：\n{user_request}\n\n场景类型：{scenario}"),
        ]

        response = self.gateway.chat(
            messages=messages,
            model_name=self.model,
            task_id="orchestrator",
            max_tokens=4096,
            temperature=0.2,
        )

        plan_data = self._parse_json(response.content)
        available_workers = self.config.get("available_workers", {})
        configured_models = getattr(self.gateway, "models", None)
        configured_model_names = (
            set(configured_models) if isinstance(configured_models, dict) else set()
        )
        tasks: list[Task] = []
        for raw_task in plan_data.get("tasks", []):
            task = Task(**_normalize_task_text_fields(raw_task))
            worker_type = task.type.strip().lower()
            if worker_type not in available_workers:
                worker_type = WORKER_TYPE_ALIASES.get(worker_type, worker_type)
            software_worker_changed = False
            if scenario == "software":
                software_type = SOFTWARE_WORKER_TYPE_ALIASES.get(worker_type)
                if software_type in available_workers:
                    worker_type = software_type
                    software_worker_changed = True
            if worker_type not in available_workers:
                raise ValueError(f"模型输出了未配置的 worker 类型: {task.type}")
            task.type = worker_type
            task = normalize_task_contract(task)

            # 模型有时会把角色名误填入 assigned_model；无效别名回退到该角色默认模型。
            default_model = available_workers.get(task.type, {}).get("default_model")
            preferred_model = (
                "" if software_worker_changed else task.assigned_model.strip()
            )
            if configured_model_names and preferred_model not in configured_model_names:
                preferred_model = ""
            task.assigned_model = self.gateway.resolve_model(
                preferred_model or default_model
            )
            tasks.append(task)

        raw_contract = plan_data.get("frontend_contract")
        plan = TaskPlan(
            summary=plan_data.get("summary", ""),
            tasks=tasks,
            frontend_contract=(
                FrontendBuildContract(**raw_contract) if raw_contract else None
            ),
        )
        self.last_response = response
        if high_risk_frontend:
            bind_and_validate_frontend_contract(plan)
        validate_collaboration_plan(plan)
        return plan

    def _parse_json(self, text: str) -> dict:
        """从文本中提取 JSON"""
        def normalize(value: object) -> dict:
            if isinstance(value, dict):
                return value
            if isinstance(value, list):
                if (
                    len(value) == 1
                    and isinstance(value[0], dict)
                    and "tasks" in value[0]
                ):
                    return value[0]
                if all(isinstance(item, dict) and "id" in item for item in value):
                    return {"summary": "", "tasks": value}
                raise ValueError(
                    "模型输出的 JSON 顶层数组必须是任务对象列表，"
                    "或只包含一个计划对象"
                )
            raise ValueError("模型输出的 JSON 顶层必须是对象或任务对象列表")

        def parse(candidate: str) -> dict | None:
            try:
                return normalize(json.loads(candidate))
            except json.JSONDecodeError:
                return None

        # 先尝试直接解析
        text = text.strip()
        parsed = parse(text)
        if parsed is not None:
            return parsed

        # 尝试从 ```json 代码块中提取
        pattern = r"```(?:json)?\n(.*?)```"
        match = re.search(pattern, text, re.DOTALL)
        if match:
            parsed = parse(match.group(1).strip())
            if parsed is not None:
                return parsed

        # 尝试从说明文字中提取第一个完整 JSON 对象或数组
        decoder = json.JSONDecoder()
        for match in re.finditer(r"[\[{]", text):
            try:
                value, _ = decoder.raw_decode(text[match.start() :])
            except json.JSONDecodeError:
                continue
            return normalize(value)

        raise ValueError(f"无法从模型输出中解析 JSON:\n{text}")
