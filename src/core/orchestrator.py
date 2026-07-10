"""总工 Orchestrator"""
from __future__ import annotations

import json
import re

import yaml

from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, Task, TaskPlan


class Orchestrator:
    """需求分析与任务拆分"""

    def __init__(self, gateway: GatewayClient, config_path: str = "config/workers.yaml", model_override: str | None = None):
        self.gateway = gateway
        self.config = self._load_config(config_path)
        self.model = (
            model_override
            or self.config.get("orchestrator", {}).get("model")
            or gateway.get_main_model()
            or "claude-fable-5"
        )
        self.system_prompt = self.config.get("orchestrator", {}).get("system_prompt", "")

    def _load_config(self, path: str) -> dict:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)

    def plan(self, user_request: str) -> TaskPlan:
        """将用户需求拆分为任务计划"""
        messages = [
            ChatMessage(role="system", content=self.system_prompt),
            ChatMessage(role="user", content=f"用户需求：\n{user_request}"),
        ]

        response = self.gateway.chat(
            messages=messages,
            model_name=self.model,
            task_id="orchestrator",
            max_tokens=4096,
            temperature=0.2,
        )

        plan_data = self._parse_json(response.content)
        tasks = [Task(**t) for t in plan_data.get("tasks", [])]

        # 如果任务没有 assigned_model，补充默认模型
        available_workers = self.config.get("available_workers", {})
        for task in tasks:
            if not task.assigned_model:
                task.assigned_model = available_workers.get(task.type, {}).get(
                    "default_model", "glm-ark"
                )

        return TaskPlan(summary=plan_data.get("summary", ""), tasks=tasks)

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
