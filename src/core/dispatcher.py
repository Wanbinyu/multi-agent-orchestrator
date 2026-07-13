"""任务调度器"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

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
                progress_callback("task_complete", payload)
            else:
                status = "✅" if result.success else "❌"
                print(f"[{status}] {tasks[task_id].type}: {tasks[task_id].title}")

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(plan.tasks))) as executor:
            futures: dict = {}

            # 提交初始无依赖任务
            for task_id in list(remaining):
                if is_ready(task_id):
                    remaining.remove(task_id)
                    _emit_start(task_id)
                    context = self._build_context(tasks[task_id], completed)
                    future = executor.submit(
                        self.worker.execute,
                        tasks[task_id],
                        output_dir,
                        context,
                        progress_callback,
                        memory_context,
                    )
                    futures[future] = task_id

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

                # 提交新就绪的任务
                for next_id in list(remaining):
                    if is_ready(next_id):
                        remaining.remove(next_id)
                        _emit_start(next_id)
                        context = self._build_context(tasks[next_id], completed)
                        futures[
                            executor.submit(
                                self.worker.execute,
                                tasks[next_id],
                                output_dir,
                                context,
                                progress_callback,
                                memory_context,
                            )
                        ] = next_id

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
        }

    def _build_context(self, task: Task, completed: dict[str, TaskResult]) -> dict[str, str]:
        """收集当前任务依赖的前置任务输出，用于 Worker 提示词渲染"""
        context: dict[str, str] = {}
        for dep_id in task.depends_on or []:
            if dep_id in completed and completed[dep_id].success:
                context[dep_id] = completed[dep_id].content
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
                        print(f"[❌] {tasks[task_id].type}: {tasks[task_id].title}")
                        print(f"    错误: {result.error}")
                    queue.append(task_id)
