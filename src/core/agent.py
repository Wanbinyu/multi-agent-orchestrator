"""对话 Agent：支持多轮上下文与工具循环"""
from __future__ import annotations

import asyncio
import json
import re
import threading
import uuid
from collections.abc import AsyncIterator
from typing import Any

from pydantic import BaseModel

from src.core.memory import MemoryContextBuilder, MemoryStore
from src.core.session import Session
from src.gateway.client import GatewayClient
from src.models.schemas import (
    ApprovalMode,
    ChatMessage,
    ChatStreamEvent,
    StreamChunk,
    TaskResult,
)
from src.tools.file_tools import write_output_files, write_text_file
from src.tools.tool_result import ToolResult
from src.tools.worker_tools import execute_tool_call


TOOL_INSTRUCTIONS = """你是 Multi-Agent Orchestrator 的会话助手，可以与用户进行多轮对话，并使用本地工具帮助用户完成任务。

可用工具（必须以 Markdown 代码块形式调用，禁止调用原生 tool_use / function_call）：

1. read_file：读取项目内文件内容。
```tool:read_file
{"path": "relative/path"}
```

2. write_file：写入文件到项目目录或用户指定的绝对路径。
```tool:write_file
{"path": "relative/path", "content": "文件内容"}
```

3. run_command：执行白名单内的命令（如 python、pytest、npm、git status 等）。
```tool:run_command
{"command": "python -m pytest"}
```

4. search_project_files：基于项目文件索引搜索相关源码文件。
```tool:search_project_files
{"query": "SessionStore"}
```

5. search_memory：搜索已保存的长期记忆。
```tool:search_memory
{"query": "用户偏好"}
```

规则：
- 只能使用上面这种 Markdown 代码块调用工具，不要输出原生 JSON tool_use 或 function_call。
- 如果用户请求需要读取、写入或执行命令，请直接输出对应的工具代码块。
- 当你说要“查看”、“读取”或“探查”某个文件/项目时，必须在同一轮回复中立即调用 read_file 或 search_project_files 工具，不能只口头描述而不调用工具。
- 当用户明确要求你生成、创建或编写文件/页面/代码时，你必须调用 write_file 工具输出文件，不能只用文字解释或只写 markdown 摘要。
- 如果用户指定了绝对路径（如 G:\\MAO_test\\index.html），直接使用该路径；如果只给了文件夹（如 G:\\MAO_test），请在该文件夹下创建合理的文件名，例如 index.html、login.js、style.css。
- read_file 也支持绝对路径，例如：
```tool:read_file
{"path": "G:\\\\MAO_test\\\\index.html"}
```
- 如果不需要工具，直接回复用户即可，不要编造工具调用。
"""


COLLABORATION_DECISION_PROMPT = """你是任务复杂度判断器。请判断用户请求是否需要拆分成多个子任务，并由多个不同专长的 AI 模型协作完成。

只需要回答一个 JSON 对象，不要解释：
{"collaborate": true}
或
{"collaborate": false}

判断标准：
- 如果请求涉及“开发一个功能/系统/页面/API/前后端/多步骤实现”，回答 true。
- 如果只是闲聊、简单问答、解释概念、读取或修改单个文件，回答 false。
"""


class AgentTurnResult(BaseModel):
    """一轮对话的执行结果"""

    session_id: str
    user_message: str
    assistant_message: str
    tool_calls: list[dict[str, Any]]
    files_written: list[str]
    input_tokens: int
    output_tokens: int
    cost_usd: float


class Agent:
    """对话 Agent"""

    def __init__(
        self,
        gateway: GatewayClient,
        session: Session,
        max_tool_iterations: int = 8,
        approval_mode: ApprovalMode | None = None,
        memory_store: MemoryStore | None = None,
    ):
        self.gateway = gateway
        self.session = session
        self.max_tool_iterations = max_tool_iterations
        self.approval_mode: ApprovalMode = approval_mode or session.approval_mode
        self.memory_store = memory_store
        self._pending_permissions: dict[str, asyncio.Event] = {}
        self._permission_results: dict[str, bool] = {}

    def _build_system_prompt(self, user_input: str = "") -> str:
        """构建系统提示，包含工具说明和相关记忆上下文"""
        parts = [TOOL_INSTRUCTIONS]
        if self.memory_store and self.memory_store.config.enabled:
            builder = MemoryContextBuilder(self.memory_store)
            memory_context = builder.build_context(user_input)
            if memory_context:
                parts.append(memory_context)
        return "\n\n".join(parts)

    def _ensure_system_prompt(self, user_input: str = "") -> None:
        """确保消息列表第一条是系统提示"""
        content = self._build_system_prompt(user_input)
        if not self.session.messages or self.session.messages[0].role != "system":
            self.session.messages.insert(0, ChatMessage(role="system", content=content))
        else:
            self.session.messages[0].content = content

    @staticmethod
    def _parse_tool_calls(content: str) -> list[dict[str, Any]]:
        """解析 assistant 回复中的工具调用块。

        兼容两种闭合方式：
        1. 标准 Markdown：```tool:xxx\\n{...}```
        2. 部分编码模型（如 ark-coding / kimi-for-coding）使用特殊 token：
           ```tool:xxx\\n{...}<|tool_calls_section_end|>
        """
        # 闭合标记：三反引号、特殊 token，或字符串结尾
        pattern = r"```tool:(\w+)\n(.*?)(?:```|<\|tool_calls_section_end\|>|$)"
        calls: list[dict[str, Any]] = []
        for match in re.finditer(pattern, content, re.DOTALL):
            tool_name = match.group(1)
            raw = match.group(2).strip()
            # 去掉残留的特殊 token
            raw = raw.replace("<|tool_calls_section_end|>", "").strip()
            try:
                params = json.loads(raw)
            except json.JSONDecodeError as e:
                calls.append({"tool": tool_name, "params": {}, "parse_error": str(e)})
                continue
            calls.append({"tool": tool_name, "params": params})
        return calls

    @staticmethod
    def _strip_toolcall_artifacts(content: str) -> str:
        """清除编码模型遗留的特殊 token，避免污染展示与上下文"""
        cleaned = content.replace("<|tool_calls_section_start|>", "")
        cleaned = cleaned.replace("<|tool_calls_section_end|>", "")
        return cleaned

    @staticmethod
    def _format_tool_result(tool_name: str, result: ToolResult) -> str:
        status = "成功" if result.success else "失败"
        lines = [f"\n[工具 {tool_name} 执行{status}]"]
        if result.success:
            lines.append(result.output or "（无输出）")
        else:
            lines.append(result.error or "未知错误")
        lines.append("[工具结果结束]\n")
        return "\n".join(lines)

    @staticmethod
    def _build_permission_message(tool_name: str, params: dict[str, Any]) -> str:
        if tool_name == "write_file":
            return f"请求写入文件：{params.get('path', '未知路径')}"
        if tool_name == "read_file":
            return f"请求读取文件：{params.get('path', '未知路径')}"
        if tool_name == "run_command":
            return f"请求执行命令：{params.get('command', '未知命令')}"
        return f"请求执行工具：{tool_name}"

    @staticmethod
    def _record_written_file(
        tool_name: str, params: dict[str, Any], result: ToolResult, files_written: list[str]
    ) -> None:
        """如果工具成功写入了文件，记录到 files_written 列表"""
        if tool_name == "write_file" and result.success:
            path = params.get("path")
            if path and path not in files_written:
                files_written.append(path)

    def _execute_tool_calls(
        self, content: str, files_written: list[str] | None = None
    ) -> tuple[str, list[dict[str, Any]]]:
        """同步执行工具调用（用于 run_turn，approve 模式下视为自动批准）"""
        calls: list[dict[str, Any]] = []
        outputs: list[str] = []

        for spec in self._parse_tool_calls(content):
            tool_name = spec["tool"]
            params = spec.get("params", {})

            if self.approval_mode == "readonly":
                calls.append({
                    "tool": tool_name,
                    "params": params,
                    "success": False,
                    "error": "只读模式：操作被拒绝",
                })
                outputs.append(f"\n[工具 {tool_name} 被拒绝：当前为只读模式]\n")
                continue

            result = execute_tool_call(tool_name, params, self.session.output_dir)
            calls.append({
                "tool": tool_name,
                "params": params,
                "success": result.success,
                "output": result.output,
                "error": result.error,
            })
            outputs.append(self._format_tool_result(tool_name, result))
            if files_written is not None:
                self._record_written_file(tool_name, params, result, files_written)

        return "\n".join(outputs), calls

    def _register_permission_request(self) -> str:
        """注册一个新的权限请求，返回 request_id"""
        request_id = f"perm-{self.session.id}-{uuid.uuid4().hex[:8]}"
        self._pending_permissions[request_id] = asyncio.Event()
        self._permission_results[request_id] = False
        return request_id

    def respond_to_permission(self, request_id: str, approved: bool) -> None:
        """用户响应权限请求"""
        self._permission_results[request_id] = approved
        event = self._pending_permissions.get(request_id)
        if event and not event.is_set():
            event.set()

    async def _wait_for_permission(self, request_id: str) -> bool:
        """等待用户对指定权限请求的响应"""
        event = self._pending_permissions.get(request_id)
        if not event:
            return False
        await event.wait()
        return self._permission_results.get(request_id, False)

    def _has_tool_calls(self, content: str) -> bool:
        return bool(re.search(r"```tool:\w+\n", content, re.DOTALL))

    def run_turn(self, user_input: str) -> AgentTurnResult:
        """执行一轮对话"""
        self._ensure_system_prompt(user_input)
        self.session.add_message("user", user_input)

        total_input = 0
        total_output = 0
        total_cost = 0.0
        tool_calls: list[dict[str, Any]] = []
        files_written: list[str] = []
        final_content = ""

        iterations = 0
        while True:
            response = self.gateway.chat_with_main_model(
                messages=self.session.messages,
                task_id=f"chat-{self.session.id}",
                max_tokens=4096,
                temperature=0.2,
            )
            total_input += response.input_tokens
            total_output += response.output_tokens
            total_cost += response.cost_usd

            self.session.add_message("assistant", response.content)
            final_content = response.content

            if not self._has_tool_calls(response.content):
                break
            if iterations >= self.max_tool_iterations:
                # 达到最大工具轮数，追加提示并要求模型直接给出最终结果
                self.session.add_message(
                    "user",
                    "已达到最大工具调用次数，请基于已获得的信息直接完成用户请求，不要再调用工具。",
                )
                response = self.gateway.chat_with_main_model(
                    messages=self.session.messages,
                    task_id=f"chat-{self.session.id}-finalize",
                    max_tokens=4096,
                    temperature=0.2,
                )
                total_input += response.input_tokens
                total_output += response.output_tokens
                total_cost += response.cost_usd
                self.session.add_message("assistant", response.content)
                final_content = response.content
                break

            tool_results_text, calls = self._execute_tool_calls(response.content, files_written)
            if not calls:
                break

            tool_calls.extend(calls)
            self.session.add_message(
                "user",
                tool_results_text + "\n\n请继续完成用户请求。",
            )
            iterations += 1

        # 把最终回复中的代码块保存到会话输出目录
        auto_written = write_output_files(final_content, self.session.output_dir)
        files_written.extend(f for f in auto_written if f not in files_written)
        if self.approval_mode == "auto" and not files_written and final_content.strip():
            files_written.append(write_text_file("response.md", final_content, self.session.output_dir))

        return AgentTurnResult(
            session_id=self.session.id,
            user_message=user_input,
            assistant_message=final_content,
            tool_calls=tool_calls,
            files_written=files_written,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )

    async def run_turn_stream(
        self,
        user_input: str,
    ) -> AsyncIterator[ChatStreamEvent]:
        """流式执行一轮对话，按 delta/done 事件产出"""
        billing_before = self.gateway.billing.summary()
        self._ensure_system_prompt(user_input)
        self.session.add_message("user", user_input)

        # 自动判断是否需要多模型协作（只读模式下不走协作，避免自动写文件）
        if self.approval_mode != "readonly" and await self._should_collaborate(user_input):
            async for event in self._run_collaboration_stream(user_input, billing_before):
                yield event
            return

        total_input = 0
        total_output = 0
        total_cost = 0.0
        tool_calls: list[dict[str, Any]] = []
        files_written: list[str] = []
        final_content = ""

        iterations = 0
        while True:
            full_content = ""
            output_before = total_output
            async for chunk in self.gateway.chat_with_main_model_stream(
                messages=self.session.messages,
                task_id=f"chat-{self.session.id}",
                max_tokens=4096,
                temperature=0.2,
            ):
                if chunk.type == "delta":
                    full_content += chunk.content or ""
                    yield ChatStreamEvent(type="delta", delta=chunk.content or "")
                elif chunk.type == "usage":
                    total_input += chunk.input_tokens
                    total_output += chunk.output_tokens
                    total_cost += chunk.cost_usd

            self.session.add_message("assistant", self._strip_toolcall_artifacts(full_content))
            final_content = self._strip_toolcall_artifacts(full_content)

            # 模型本轮返回了 token 但没有可解析文本，可能是原生 tool_use/reasoning 未捕获
            if (
                not full_content.strip()
                and total_output > output_before
            ):
                yield ChatStreamEvent(
                    type="error",
                    error="模型未返回可解析文本（可能输出了原生工具调用或推理内容），请重试或换一个模型。",
                )
                return

            if not self._has_tool_calls(full_content):
                break
            if iterations >= self.max_tool_iterations:
                # 达到最大工具轮数，追加提示并要求模型直接给出最终结果
                self.session.add_message(
                    "user",
                    "已达到最大工具调用次数，请基于已获得的信息直接完成用户请求，不要再调用工具。",
                )
                full_content = ""
                async for chunk in self.gateway.chat_with_main_model_stream(
                    messages=self.session.messages,
                    task_id=f"chat-{self.session.id}-finalize",
                    max_tokens=4096,
                    temperature=0.2,
                ):
                    if chunk.type == "delta":
                        full_content += chunk.content or ""
                        yield ChatStreamEvent(type="delta", delta=chunk.content or "")
                    elif chunk.type == "usage":
                        total_input += chunk.input_tokens
                        total_output += chunk.output_tokens
                        total_cost += chunk.cost_usd
                final_content = self._strip_toolcall_artifacts(full_content)
                self.session.add_message("assistant", final_content)
                break

            # 流式执行工具调用，期间可能产出 permission_request 事件
            tool_specs = self._parse_tool_calls(full_content)
            calls: list[dict[str, Any]] = []
            tool_results_parts: list[str] = []

            for spec in tool_specs:
                tool_name = spec["tool"]
                params = spec.get("params", {})
                parse_error = spec.get("parse_error")

                if parse_error:
                    call = {
                        "tool": tool_name,
                        "params": {},
                        "success": False,
                        "error": f"参数解析失败：{parse_error}",
                    }
                    calls.append(call)
                    tool_results_parts.append(
                        f"\n[工具 {tool_name} 参数解析失败：{parse_error}]\n"
                    )
                    continue

                if self.approval_mode == "readonly":
                    call = {
                        "tool": tool_name,
                        "params": params,
                        "success": False,
                        "error": "只读模式：操作被拒绝",
                    }
                    calls.append(call)
                    tool_results_parts.append(
                        f"\n[工具 {tool_name} 被拒绝：当前为只读模式]\n"
                    )
                    continue

                if self.approval_mode == "approve":
                    request_id = self._register_permission_request()
                    yield ChatStreamEvent(
                        type="permission_request",
                        permission_request={
                            "request_id": request_id,
                            "tool": tool_name,
                            "params": params,
                            "message": self._build_permission_message(tool_name, params),
                        },
                    )
                    approved = await self._wait_for_permission(request_id)
                    if not approved:
                        call = {
                            "tool": tool_name,
                            "params": params,
                            "success": False,
                            "error": "用户拒绝执行",
                        }
                        calls.append(call)
                        tool_results_parts.append(f"\n[工具 {tool_name} 被用户拒绝]\n")
                        continue

                result = await asyncio.to_thread(
                    execute_tool_call, tool_name, params, self.session.output_dir
                )
                call = {
                    "tool": tool_name,
                    "params": params,
                    "success": result.success,
                    "output": result.output,
                    "error": result.error,
                }
                calls.append(call)
                tool_results_parts.append(self._format_tool_result(tool_name, result))
                self._record_written_file(tool_name, params, result, files_written)

            if not calls:
                break

            tool_calls.extend(calls)
            self.session.add_message(
                "user",
                "".join(tool_results_parts) + "\n\n请继续完成用户请求。",
            )
            iterations += 1

        # 仅在 auto 模式下自动落盘；approve/readonly 模式下不自动写 response.md
        if self.approval_mode == "auto":
            auto_written = await asyncio.to_thread(
                write_output_files, final_content, self.session.output_dir
            )
            files_written.extend(f for f in auto_written if f not in files_written)
            if not files_written and final_content.strip():
                files_written.append(
                    await asyncio.to_thread(
                        write_text_file, "response.md", final_content, self.session.output_dir
                    )
                )

        yield ChatStreamEvent(
            type="done",
            assistant_message=final_content,
            tool_calls=tool_calls,
            files_written=files_written,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )

    async def _should_collaborate(self, user_input: str) -> bool:
        """让主模型判断是否需要多模型协作"""
        messages = [
            ChatMessage(role="system", content=COLLABORATION_DECISION_PROMPT),
            ChatMessage(role="user", content=user_input),
        ]
        try:
            response = await asyncio.to_thread(
                self.gateway.chat_with_main_model,
                messages=messages,
                task_id=f"chat-{self.session.id}-decide",
                max_tokens=64,
                temperature=0.1,
            )
            content = response.content.strip()
            # 尝试直接解析 JSON
            if content.startswith("{"):
                data = json.loads(content)
                return bool(data.get("collaborate"))
            # 兜底：关键字匹配
            return "yes" in content.lower() or "true" in content.lower()
        except Exception:
            # 判断失败时保守走单模型路径
            return False

    async def _run_collaboration_stream(
        self,
        user_input: str,
        billing_before: dict[str, Any],
    ) -> AsyncIterator[ChatStreamEvent]:
        """多模型协作流：Orchestrator -> Dispatcher -> Reviewer"""
        from src.core.dispatcher import Dispatcher
        from src.core.orchestrator import Orchestrator
        from src.core.reviewer import Reviewer
        from src.core.worker import Worker, load_workers_config

        # 构建记忆上下文
        memory_context = ""
        if self.memory_store and self.memory_store.config.enabled:
            builder = MemoryContextBuilder(self.memory_store)
            memory_context = builder.build_context(user_input)

        # 1. Orchestrator 规划
        orchestrator = Orchestrator(self.gateway)
        plan = await asyncio.to_thread(
            orchestrator.plan,
            user_request=user_input,
            memory_context=memory_context,
        )
        yield ChatStreamEvent(
            type="plan",
            plan={
                "summary": plan.summary,
                "tasks": [
                    {
                        "id": t.id,
                        "type": t.type,
                        "title": t.title,
                        "assigned_model": t.assigned_model,
                    }
                    for t in plan.tasks
                ],
            },
        )

        # 1.5 协作前置批量确认：approve 模式下，dispatch 前一次性征求用户同意
        if self.approval_mode == "approve":
            request_id = self._register_permission_request()
            yield ChatStreamEvent(
                type="permission_request",
                permission_request={
                    "request_id": request_id,
                    "tool": "collaboration",
                    "params": {
                        "output_dir": self.session.output_dir,
                        "task_count": len(plan.tasks),
                        "tasks": [
                            {"id": t.id, "type": t.type, "title": t.title}
                            for t in plan.tasks
                        ],
                    },
                    "message": (
                        f"将执行 {len(plan.tasks)} 个子任务并自动写入文件到 "
                        f"{self.session.output_dir}，是否批准？"
                    ),
                },
            )
            approved = await self._wait_for_permission(request_id)
            if not approved:
                self.session.add_message("assistant", "协作已取消。")
                yield ChatStreamEvent(
                    type="done",
                    assistant_message="协作已取消。",
                    tool_calls=[],
                    files_written=[],
                    input_tokens=0,
                    output_tokens=0,
                    cost_usd=0.0,
                )
                return

        # 2. Dispatcher 并发执行（带进度回调）
        loop = asyncio.get_event_loop()
        queue: asyncio.Queue = asyncio.Queue()
        error_info: dict[str, str] | None = None

        def _progress(event_type: str, payload: dict[str, Any]):
            asyncio.run_coroutine_threadsafe(queue.put((event_type, payload)), loop)

        def _dispatch():
            nonlocal error_info
            try:
                workers_config = load_workers_config()
                worker = Worker(self.gateway, workers_config)
                dispatcher = Dispatcher(worker, max_workers=4)
                return dispatcher.dispatch(
                    plan,
                    output_dir=self.session.output_dir,
                    progress_callback=_progress,
                    memory_context=memory_context,
                )
            except Exception as exc:  # noqa: BLE001
                error_info = {"error": str(exc)}
                _progress("__error__", error_info)
            finally:
                _progress("__done__", {})

        thread = threading.Thread(target=_dispatch, daemon=True)
        thread.start()

        results: list[TaskResult] = []
        while True:
            event_type, payload = await queue.get()
            if event_type == "__done__":
                break
            if event_type == "__error__":
                yield ChatStreamEvent(type="error", error=payload.get("error", "未知错误"))
                return
            if event_type == "task_complete":
                task_id = payload["id"]
                task = next((t for t in plan.tasks if t.id == task_id), None)
                if task:
                    results.append(
                        TaskResult(
                            task=task,
                            success=payload.get("success", False),
                            content=payload.get("content", ""),
                            error=payload.get("error", ""),
                            files_written=payload.get("files_written", []),
                        )
                    )
            yield ChatStreamEvent(type=event_type, task=payload)

        # 3. Reviewer 整合
        reviewer = Reviewer(self.gateway)
        review = await asyncio.to_thread(
            reviewer.review,
            user_request=user_input,
            plan=plan,
            results=results,
        )
        yield ChatStreamEvent(
            type="review_complete",
            review={
                "passed": review.passed,
                "issues": review.issues,
                "final_output": review.final_output,
            },
        )

        # 4. 追加最终答案到 Session
        self.session.add_message("assistant", review.final_output)

        # 5. 计算本次协作成本
        billing_after = self.gateway.billing.summary()
        total_input = billing_after["total_input_tokens"] - billing_before["total_input_tokens"]
        total_output = billing_after["total_output_tokens"] - billing_before["total_output_tokens"]
        total_cost = billing_after["total_cost_usd"] - billing_before["total_cost_usd"]

        all_files: list[str] = []
        for r in results:
            all_files.extend(r.files_written)

        # 6. 把 Reviewer 最终输出中的代码块也落盘到会话输出目录
        if self.approval_mode == "auto" and review.final_output:
            final_files = await asyncio.to_thread(
                write_output_files, review.final_output, self.session.output_dir
            )
            all_files.extend(f for f in final_files if f not in all_files)
            if not final_files and review.final_output.strip():
                all_files.append(
                    await asyncio.to_thread(
                        write_text_file, "response.md", review.final_output, self.session.output_dir
                    )
                )

        yield ChatStreamEvent(
            type="done",
            assistant_message=review.final_output,
            tool_calls=[],
            files_written=all_files,
            input_tokens=total_input,
            output_tokens=total_output,
            cost_usd=total_cost,
        )
