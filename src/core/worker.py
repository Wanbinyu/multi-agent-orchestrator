"""Worker 执行器"""
from __future__ import annotations

import json
import re
from typing import Any, Callable

import yaml

from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, Task, TaskResult
from src.tools.file_tools import write_output_files, write_text_file
from src.tools.worker_tools import execute_tool_call


ProgressCallback = Callable[[str, dict[str, Any]], None]


class Worker:
    """执行单一子任务"""

    def __init__(self, gateway: GatewayClient, workers_config: dict):
        self.gateway = gateway
        self.workers_config = workers_config

    def execute(
        self,
        task: Task,
        output_dir: str = "output",
        context: dict[str, str] | None = None,
        progress_callback: ProgressCallback | None = None,
        memory_context: str | None = None,
    ) -> TaskResult:
        """执行一个子任务"""
        worker_cfg = self.workers_config.get(task.type)
        if not worker_cfg:
            return TaskResult(
                task=task,
                success=False,
                content="",
                error=f"未知的 worker 类型: {task.type}",
            )

        system_prompt = worker_cfg.get("system_prompt", "")
        tools = worker_cfg.get("tools", ["write_file"])
        context = context or {}

        # 将 {{task_id.output}} 占位符替换为前置任务输出
        task_input = _render_template(task.input, context)
        task_output_format = _render_template(task.output_format, context)
        task_acceptance = _render_template(task.acceptance, context)

        # 构造完整输入
        user_content = f"""任务标题：{task.title}

任务描述：
{task_input}

输出格式要求：
{task_output_format or "无特殊要求"}

验收标准：
{task_acceptance or "无"}
"""
        if context:
            context_lines = ["\n前置任务输出（供参考）："]
            for dep_id, dep_content in context.items():
                context_lines.append(f"\n--- [{dep_id}] 开始 ---")
                context_lines.append(dep_content[:4000] if len(dep_content) > 4000 else dep_content)
                context_lines.append(f"--- [{dep_id}] 结束 ---\n")
            user_content += "\n".join(context_lines)

        if memory_context:
            user_content = f"【项目记忆与上下文】\n{memory_context}\n\n" + user_content

        user_content += f"""
{build_tool_instructions(tools)}

请直接输出可执行的代码或结果，使用 Markdown 代码块包裹代码。"""

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]

        try:
            model_name = self.gateway.resolve_model(task.assigned_model)
            response = self.gateway.chat(
                messages=messages,
                model_name=model_name,
                task_id=task.id,
                max_tokens=4096,
                temperature=0.2,
            )

            # 处理工具调用
            task_output_dir = f"{output_dir}/{task.type}_{task.id}"
            content, tool_results = process_tool_calls(
                response.content,
                task_output_dir,
                allowed_prefixes=worker_cfg.get("allowed_commands"),
            )

            # 收集通过 write_file 工具实际写入的文件
            files_from_tools: list[str] = []
            for tr in tool_results:
                if tr["tool"] == "write_file" and tr["success"]:
                    path = tr["params"].get("path")
                    if path and path not in files_from_tools:
                        files_from_tools.append(path)

            # 写入代码块到文件
            files_written = write_output_files(content, task_output_dir)

            # 兜底：如果没有解析到代码块，把完整响应内容保存为 content.txt
            if not files_written and content.strip():
                files_written.append(write_text_file("content.txt", content, task_output_dir))

            files_written.extend(f for f in files_from_tools if f not in files_written)

            # 如果既没有内容也没有文件，判定为执行失败
            if not content.strip() and not files_written:
                return TaskResult(
                    task=task,
                    success=False,
                    content="",
                    error="模型未返回可执行内容或文件",
                    response=response,
                    files_written=[],
                )

            return TaskResult(
                task=task,
                success=True,
                content=content,
                response=response,
                files_written=files_written,
            )
        except Exception as e:
            return TaskResult(
                task=task,
                success=False,
                content="",
                error=str(e),
            )

    def _task_to_payload(self, task: Task, result: TaskResult | None) -> dict[str, Any]:
        payload = {
            "id": task.id,
            "type": task.type,
            "title": task.title,
            "assigned_model": task.assigned_model,
        }
        if result:
            payload.update({
                "success": result.success,
                "error": result.error,
                "files_written": result.files_written,
                "content": result.content,
            })
        return payload


def build_tool_instructions(tools: list[str]) -> str:
    """根据可用工具生成提示词"""
    if not tools:
        return ""

    lines = ["你可以使用以下工具（在回复中以 Markdown 代码块形式调用）："]
    if "write_file" in tools:
        lines.append(
            '- write_file：写入文件。格式：\\n```tool:write_file\\n{"path": "relative/path", "content": "文件内容"}\\n```\\n'
            "如果用户指定了绝对路径（如 G:\\\\MAO_test\\\\login.js），请直接使用该路径；否则写到当前任务输出目录。"
        )
    if "read_file" in tools:
        lines.append(
            '- read_file：读取已有文件内容。格式：\\n```tool:read_file\\n{"path": "relative/path"}\\n```'
        )
    if "run_command" in tools:
        lines.append(
            '- run_command：运行测试或构建命令。格式：\\n```tool:run_command\\n{"command": "pytest"}\\n```\\n'
            "注意：命令必须在白名单内，白名单外命令会被拒绝。"
        )
    if "search_project_files" in tools:
        lines.append(
            '- search_project_files：基于项目索引搜索相关源码文件。格式：\\n```tool:search_project_files\\n{"query": "SessionStore"}\\n```'
        )
    if "search_memory" in tools:
        lines.append(
            '- search_memory：搜索已保存的长期记忆。格式：\\n```tool:search_memory\\n{"query": "用户偏好"}\\n```'
        )
    return "\n".join(lines)


def process_tool_calls(
    content: str,
    base_dir: str,
    allowed_prefixes: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """解析并执行工具调用，返回处理后的内容和工具结果列表"""
    pattern = r"```tool:(\w+)\n(.*?)```"
    tool_results = []

    def replacer(match: re.Match) -> str:
        tool_name = match.group(1)
        try:
            params = json.loads(match.group(2).strip())
        except json.JSONDecodeError as e:
            tool_results.append({
                "tool": tool_name,
                "params": {},
                "success": False,
                "output": "",
                "error": f"参数解析失败：{e}",
            })
            return f"\n[工具调用参数解析失败：{e}]\n"

        result = execute_tool_call(tool_name, params, base_dir, allowed_prefixes)
        tool_results.append({
            "tool": tool_name,
            "params": params,
            "success": result.success,
            "output": result.output,
            "error": result.error,
        })

        output_lines = [f"\n[工具 {tool_name} 执行结果]"]
        if result.success:
            output_lines.append(result.output or "（无输出）")
        else:
            output_lines.append(f"失败：{result.error}")
        output_lines.append("[工具结果结束]\n")
        return "\n".join(output_lines)

    processed = re.sub(pattern, replacer, content, flags=re.DOTALL)
    return processed, tool_results


def load_workers_config(path: str = "config/workers.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("available_workers", {})


def _render_template(text: str, context: dict[str, str]) -> str:
    """将文本中的 {{task_id.output}} 占位符替换为前置任务输出"""
    if not text:
        return text

    def replacer(match: re.Match) -> str:
        task_id = match.group(1)
        return context.get(task_id, match.group(0))

    return re.sub(r"\{\{(\w+)\.output\}\}", replacer, text)
