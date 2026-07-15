"""Worker 执行器"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Callable

import yaml

from src.gateway.client import GatewayClient
from src.models.schemas import ChatMessage, Task, TaskResult
from src.tools.file_tools import write_text_file
from src.tools.registry import tool_registry
from src.tools.worker_tools import execute_tool_call


ProgressCallback = Callable[[str, dict[str, Any]], None]


class Worker:
    """执行单一子任务"""

    def __init__(self, gateway: GatewayClient, workers_config: dict, max_tool_iterations: int = 5):
        self.gateway = gateway
        self.workers_config = workers_config
        self.max_tool_iterations = max_tool_iterations

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
        tools = _expand_legacy_read_tools(worker_cfg.get("tools", ["write_file"]))
        context = context or {}
        try:
            model_name = self.gateway.resolve_model(task.assigned_model)
        except Exception as exc:
            return TaskResult(task=task, success=False, content="", error=str(exc))
        native_kwargs = _worker_native_tool_kwargs(self.gateway, model_name, tools)
        if native_kwargs:
            tool_instructions = "可用工具已通过模型原生 tool_use 协议提供，请使用结构化工具调用。"
        else:
            tool_instructions = build_tool_instructions(tools)

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
{tool_instructions}

执行规则：
- 探查目录时优先使用 list_dir 或 glob_files，读取具体文件时使用 read_file。
- 工具执行结果会返回给你；收到结果后必须继续完成任务，不能停在工具调用。
- 任务需要创建或修改文件时，必须使用 write_file/edit_file，并使用有意义的文件名。
- 禁止只在正文中输出代码块代替写文件；正文代码块不会自动生成项目文件。
- 不需要创建文件的分析、审查或写作任务可以直接输出最终文本。"""

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_content),
        ]

        try:
            task_output_dir = str(Path(output_dir) / f"{task.type}_{task.id}")
            Path(task_output_dir).mkdir(parents=True, exist_ok=True)
            files_written: list[str] = []
            total_input = 0
            total_output = 0
            total_cost = 0.0
            final_content = ""
            last_response = None
            iterations = 0
            recovery_requested = False
            requires_file_output = _task_requires_file_output(task)

            while True:
                response = self.gateway.chat(
                    messages=messages,
                    model_name=model_name,
                    task_id=task.id,
                    max_tokens=4096,
                    temperature=0.2,
                    **native_kwargs,
                )
                last_response = response
                total_input += response.input_tokens
                total_output += response.output_tokens
                total_cost += response.cost_usd

                processed, tool_results = process_tool_calls(
                    response.content,
                    task_output_dir,
                    allowed_prefixes=worker_cfg.get("allowed_commands"),
                    allowed_tools=tools,
                )
                _collect_written_files(tool_results, task_output_dir, files_written)

                if tool_results:
                    messages.append(ChatMessage(role="assistant", content=response.content))
                    messages.append(ChatMessage(
                        role="user",
                        content=processed + "\n\n请根据工具结果继续完成任务。",
                    ))
                    iterations += 1
                    if iterations >= self.max_tool_iterations:
                        messages.append(ChatMessage(
                            role="user",
                            content="已达到工具调用上限。不要再调用工具，请直接给出最终结果和完成情况。",
                        ))
                        native_kwargs = {}
                    else:
                        continue

                final_content = processed if not tool_results else ""
                if tool_results and iterations >= self.max_tool_iterations:
                    final_response = self.gateway.chat(
                        messages=messages,
                        model_name=model_name,
                        task_id=f"{task.id}-finalize",
                        max_tokens=4096,
                        temperature=0.2,
                    )
                    last_response = final_response
                    total_input += final_response.input_tokens
                    total_output += final_response.output_tokens
                    total_cost += final_response.cost_usd
                    final_content = final_response.content

                # 项目代码不得靠正文代码块落盘；给模型一次显式纠正机会。
                if (
                    not files_written
                    and requires_file_output
                    and "write_file" in tools
                    and _contains_code_fence(final_content)
                    and not recovery_requested
                    and iterations < self.max_tool_iterations
                ):
                    messages.append(ChatMessage(role="assistant", content=final_content))
                    messages.append(ChatMessage(
                        role="user",
                        content=(
                            "你输出了代码块但没有创建文件。请立即使用 write_file 为每个项目文件写入"
                            "有意义的路径；不要再次只输出代码块。"
                        ),
                    ))
                    recovery_requested = True
                    iterations += 1
                    continue
                break

            if last_response is None:  # pragma: no cover - defensive
                raise RuntimeError("Worker 未获得模型响应")

            aggregate_response = last_response.model_copy(update={
                "content": final_content,
                "input_tokens": total_input,
                "output_tokens": total_output,
                "cost_usd": total_cost,
            })

            # 不丢弃模型最终文本，但绝不再生成 generated_N 文件。
            fallback_path = ""
            if not files_written and final_content.strip():
                fallback_path = write_text_file("content.txt", final_content, task_output_dir)
                files_written.append(fallback_path)

            if not final_content.strip() and not files_written:
                return TaskResult(
                    task=task,
                    success=False,
                    content="",
                    error="模型未返回可执行内容或文件",
                    response=aggregate_response,
                    files_written=[],
                )

            if (
                fallback_path
                and requires_file_output
                and "write_file" in tools
                and _contains_code_fence(final_content)
            ):
                return TaskResult(
                    task=task,
                    success=False,
                    content=final_content,
                    error="模型未按要求使用 write_file 创建项目文件；原始内容已保存在 content.txt",
                    response=aggregate_response,
                    files_written=files_written,
                )

            return TaskResult(
                task=task,
                success=True,
                content=final_content,
                response=aggregate_response,
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
    """根据可用工具生成提示词（从注册表自动生成）"""
    if not tools:
        return ""

    instructions = tool_registry.build_instructions(tools)
    if not instructions:
        return ""

    lines = ["你可以使用以下工具（在回复中以 Markdown 代码块形式调用）：", ""]
    # build_instructions 已包含工具列表，直接追加特定说明
    lines.append(instructions.rstrip())
    lines.append("")
    lines.append(
        "如果用户指定了绝对路径（如 G:\\\\MAO_test\\\\login.js），请直接使用该路径；否则写到当前任务输出目录。"
    )
    return "\n".join(lines)


def _expand_legacy_read_tools(tools: list[str]) -> list[str]:
    """旧配置已授予读取能力时，补齐新的只读目录工具。"""
    expanded = list(dict.fromkeys(tools))
    if any(name in expanded for name in ("read_file", "search_project_files", "search_memory")):
        for name in ("list_dir", "glob_files", "grep_content", "read_file"):
            if name not in expanded:
                expanded.append(name)
    return expanded


def _worker_native_tool_kwargs(
    gateway: GatewayClient, model_name: str, tools: list[str]
) -> dict[str, Any]:
    """为支持原生 tool_use 的 Worker 构造 Provider 工具 schema。"""
    try:
        model_config = gateway.get_model_config(model_name)
        enabled = model_config.native_tools
        if enabled is None:
            enabled = "tool_use" in model_config.capabilities
        if not enabled:
            return {}
        provider = gateway.providers.get(model_config.provider)
        if provider is None or provider.config.type not in ("anthropic", "openai"):
            return {}
        return {"tools": tool_registry.build_tool_schemas(provider.config.type, tools)}
    except (AttributeError, KeyError, TypeError):
        return {}


def _contains_code_fence(content: str) -> bool:
    return bool(re.search(r"```(?!tool:)[\w+-]*\n", content))


def _task_requires_file_output(task: Task) -> bool:
    """仅对明确的实现型 Worker 强制使用 write_file，避免误伤分析/写作。"""
    implementation_types = {
        "frontend", "frontend_dev", "backend", "backend_dev", "tester", "developer",
    }
    if task.type in implementation_types:
        return True
    combined = f"{task.input}\n{task.output_format}\n{task.acceptance}".lower()
    explicit_markers = (
        "创建文件", "生成文件", "写入文件", "保存到文件",
        "create file", "write file", "save to file",
    )
    return any(marker in combined for marker in explicit_markers)


def _collect_written_files(
    tool_results: list[dict], base_dir: str, files_written: list[str]
) -> None:
    for result in tool_results:
        if result.get("tool") not in ("write_file", "edit_file") or not result.get("success"):
            continue
        raw_path = result.get("params", {}).get("path")
        if not raw_path:
            continue
        path = Path(raw_path)
        resolved = path.resolve() if path.is_absolute() else (Path(base_dir) / path).resolve()
        value = str(resolved)
        if value not in files_written:
            files_written.append(value)


def process_tool_calls(
    content: str,
    base_dir: str,
    allowed_prefixes: list[str] | None = None,
    allowed_tools: list[str] | None = None,
) -> tuple[str, list[dict]]:
    """解析并执行工具调用，返回处理后的内容和工具结果列表"""
    pattern = r"```tool:(\w+)\n(.*?)(?:```|<\|tool_calls_section_end\|>|$)"
    tool_results = []

    def replacer(match: re.Match) -> str:
        tool_name = match.group(1)
        if allowed_tools is not None and tool_name not in allowed_tools:
            tool_results.append({
                "tool": tool_name,
                "params": {},
                "success": False,
                "output": "",
                "error": f"Worker 未获授权使用工具：{tool_name}",
            })
            return f"\n[工具 {tool_name} 被拒绝：Worker 未获授权]\n"
        try:
            raw_params = match.group(2).replace("<|tool_calls_section_end|>", "").strip()
            params = json.loads(raw_params)
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
