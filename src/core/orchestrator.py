"""总工 Orchestrator"""
from __future__ import annotations

import json
import re

import yaml

from src.gateway.client import GatewayClient
from src.core.collaboration import normalize_task_contract, validate_collaboration_plan
from src.core.config_paths import resolve_workers_config_path
from src.models.schemas import ChatMessage, Task, TaskPlan


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

    def __init__(self, gateway: GatewayClient, config_path: str = "config/workers.yaml", model_override: str | None = None):
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

    def _load_config(self, path: str) -> dict:
        with resolve_workers_config_path(path).open("r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def plan(self, user_request: str, memory_context: str | None = None) -> TaskPlan:
        """将用户需求拆分为任务计划"""
        scenario = _detect_scenario(user_request)
        scenario_instruction = SCENARIO_INSTRUCTIONS.get(scenario, "")
        system_prompt = f"{self.system_prompt}\n{scenario_instruction}".strip()
        if memory_context:
            system_prompt = f"{system_prompt}\n\n{memory_context}".strip()

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
        tasks = [normalize_task_contract(Task(**t)) for t in plan_data.get("tasks", [])]

        # 如果任务没有 assigned_model，补充默认模型
        available_workers = self.config.get("available_workers", {})
        for task in tasks:
            if not task.assigned_model:
                default_model = available_workers.get(task.type, {}).get(
                    "default_model"
                )
                task.assigned_model = self.gateway.resolve_model(default_model)

        plan = TaskPlan(summary=plan_data.get("summary", ""), tasks=tasks)
        validate_collaboration_plan(plan)
        return plan

    def _parse_json(self, text: str) -> dict:
        """从文本中提取 JSON"""
        # 先尝试直接解析
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
