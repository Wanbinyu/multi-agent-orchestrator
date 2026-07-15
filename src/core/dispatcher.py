"""任务调度器"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from src.core.collaboration import find_parallel_ownership_conflicts
from src.core.worker import Worker, ProgressCallback as WorkerProgressCallback
from src.models.schemas import Task, TaskPlan, TaskResult


ProgressCallback = Callable[[str, dict[str, Any]], None]


class Dispatcher:
    """按任务依赖图（DAG）调度多个 Worker"""

    def __init__(self, worker: Worker, max_workers: int = 4):
        self.worker = worker
        self.max_workers = max_workers

    def dispatch(
        self,
        plan: TaskPlan,
        output_dir: str = "output",
        progress_callback: ProgressCallback | None = None,
        memory_context: str | None = None,
    ) -> list[TaskResult]:
        """按依赖关系执行任务计划"""
        if not plan.tasks:
            return []

        def reject_plan(error: str) -> list[TaskResult]:
            rejected = [
                TaskResult(task=task, success=False, content="", error=error)
                for task in plan.tasks
            ]
            if progress_callback:
                for result in rejected:
                    payload = self._task_payload(result.task)
                    payload.update({
                        "success": False,
                        "error": error,
                        "files_written": [],
                        "content": "",
                        "tool_calls": [],
                        "attempts": 1,
                        "retry_errors": [],
                        "acceptance_evidence": [],
                    })
                    progress_callback("task_complete", payload)
            return rejected

        ids = [task.id for task in plan.tasks]
        duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
        if duplicates:
            return reject_plan(f"任务 ID 重复，计划无法执行：{', '.join(duplicates)}")

        conflicts = find_parallel_ownership_conflicts(plan)
        if conflicts:
            left, right, path = conflicts[0]
            return reject_plan(
                "任务因计划边界冲突无法被执行："
                f"并行子任务 {left} 与 {right} 共同拥有 {path}"
            )

        tasks = {t.id: t for t in plan.tasks}
        remaining = set(tasks.keys())
        completed: dict[str, TaskResult] = {}
        results: list[TaskResult] = []

        def is_ready(task_id: str) -> bool:
            """任务的所有依赖都已成功完成"""
            deps = tasks[task_id].depends_on or []
            return all(dep in completed and completed[dep].success for dep in deps)

        def _emit_start(task_id: str):
            if progress_callback:
                progress_callback("task_start", self._task_payload(tasks[task_id]))
            else:
                print(f"[开始] {tasks[task_id].type}: {tasks[task_id].title}")

        def _emit_complete(task_id: str, result: TaskResult):
            if progress_callback:
                payload = self._task_payload(tasks[task_id])
                payload["success"] = result.success
                payload["error"] = result.error
                payload["files_written"] = result.files_written
                payload["content"] = result.content
                payload["tool_calls"] = result.tool_calls
                payload["attempts"] = result.attempts
                payload["retry_errors"] = result.retry_errors
                payload["acceptance_evidence"] = result.acceptance_evidence
                progress_callback("task_complete", payload)
            else:
                status = "成功" if result.success else "失败"
                print(f"[{status}] {tasks[task_id].type}: {tasks[task_id].title}")

        def execute_with_retry(task_id: str, context: dict[str, str]) -> TaskResult:
            task = tasks[task_id]
            retry_errors: list[str] = []
            accumulated_tool_calls: list[dict[str, Any]] = []
            accumulated_files: list[str] = []
            accumulated_acceptance: list[str] = []
            for attempt in range(1, task.max_retries + 2):
                try:
                    result = self.worker.execute(
                        task,
                        output_dir,
                        context,
                        progress_callback,
                        memory_context,
                    )
                except Exception as exc:  # noqa: BLE001
                    result = TaskResult(
                        task=task,
                        success=False,
                        content="",
                        error=str(exc),
                    )
                accumulated_tool_calls.extend(result.tool_calls)
                accumulated_files = list(dict.fromkeys([
                    *accumulated_files, *result.files_written,
                ]))
                accumulated_acceptance = list(dict.fromkeys([
                    *accumulated_acceptance, *result.acceptance_evidence,
                ]))
                result.attempts = attempt
                result.retry_errors = [*retry_errors]
                result.tool_calls = list(accumulated_tool_calls)
                result.files_written = list(accumulated_files)
                result.acceptance_evidence = list(accumulated_acceptance)
                if result.success or attempt > task.max_retries or not _is_retryable(result.error):
                    return result
                retry_errors.append(result.error)
                if progress_callback:
                    payload = self._task_payload(task)
                    payload.update({
                        "attempt": attempt + 1,
                        "max_attempts": task.max_retries + 1,
                        "previous_error": result.error,
                    })
                    progress_callback("task_retry", payload)
            raise RuntimeError("不可达的重试状态")  # pragma: no cover

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(plan.tasks))) as executor:
            futures: dict = {}

            def submit_ready() -> None:
                ready = sorted(task_id for task_id in remaining if is_ready(task_id))
                if not ready:
                    return
                running_exclusive = any(
                    not tasks[task_id].parallel_safe for task_id in futures.values()
                )
                if running_exclusive:
                    return
                if not futures:
                    exclusive = next(
                        (task_id for task_id in ready if not tasks[task_id].parallel_safe),
                        None,
                    )
                    selected = [exclusive] if exclusive else ready
                else:
                    selected = [
                        task_id for task_id in ready if tasks[task_id].parallel_safe
                    ]
                for task_id in selected:
                    remaining.remove(task_id)
                    _emit_start(task_id)
                    context = self._build_context(tasks[task_id], completed)
                    future = executor.submit(
                        execute_with_retry,
                        task_id,
                        context,
                    )
                    futures[future] = task_id

            submit_ready()

            while futures:
                future = next(as_completed(futures))
                task_id = futures.pop(future)
                result = future.result()
                results.append(result)
                completed[task_id] = result

                _emit_complete(task_id, result)
                if not result.success:
                    if not progress_callback:
                        print(f"    错误: {result.error}")
                    self._cascade_failure(task_id, tasks, remaining, completed, results, progress_callback)

                submit_ready()

        # 如果还有剩余任务，说明存在循环依赖或无法到达的任务
        for task_id in remaining:
            result = TaskResult(
                task=tasks[task_id],
                success=False,
                content="",
                error="任务因依赖关系无法被执行（可能存在循环依赖或上游失败）",
            )
            results.append(result)
            completed[task_id] = result
            _emit_complete(task_id, result)

        # 按任务 id 排序返回
        results.sort(key=lambda r: r.task.id)
        return results

    def _task_payload(self, task: Task) -> dict[str, Any]:
        return {
            "id": task.id,
            "type": task.type,
            "title": task.title,
            "assigned_model": task.assigned_model,
            "execution_mode": task.execution_mode,
            "owned_paths": task.owned_paths,
            "parallel_safe": task.parallel_safe,
            "max_retries": task.max_retries,
        }

    def _build_context(self, task: Task, completed: dict[str, TaskResult]) -> dict[str, str]:
        """收集当前任务依赖的前置任务输出，用于 Worker 提示词渲染"""
        context: dict[str, str] = {}
        for dep_id in task.depends_on or []:
            if dep_id in completed and completed[dep_id].success:
                context[dep_id] = completed[dep_id].content
                if completed[dep_id].files_written:
                    context[dep_id] += "\n\n产出文件：\n" + "\n".join(
                        completed[dep_id].files_written
                    )
        return context

    def _cascade_failure(
        self,
        failed_id: str,
        tasks: dict[str, Task],
        remaining: set[str],
        completed: dict[str, TaskResult],
        results: list[TaskResult],
        progress_callback: ProgressCallback | None = None,
    ) -> None:
        """将失败任务的下游任务标记为失败"""
        queue = [failed_id]
        while queue:
            current = queue.pop(0)
            for task_id in list(remaining):
                deps = tasks[task_id].depends_on or []
                if current in deps:
                    remaining.remove(task_id)
                    result = TaskResult(
                        task=tasks[task_id],
                        success=False,
                        content="",
                        error=f"依赖任务 {current} 失败",
                    )
                    results.append(result)
                    completed[task_id] = result
                    if progress_callback:
                        payload = self._task_payload(tasks[task_id])
                        payload["success"] = False
                        payload["error"] = result.error
                        payload["files_written"] = []
                        progress_callback("task_complete", payload)
                    else:
                        print(f"[失败] {tasks[task_id].type}: {tasks[task_id].title}")
                        print(f"    错误: {result.error}")
                    queue.append(task_id)


def _is_retryable(error: str) -> bool:
    normalized = error.casefold()
    markers = (
        "timeout",
        "timed out",
        "超时",
        "connection",
        "连接",
        "temporarily",
        "临时",
        "rate limit",
        "429",
        "502",
        "503",
        "504",
    )
    return any(marker in normalized for marker in markers)
