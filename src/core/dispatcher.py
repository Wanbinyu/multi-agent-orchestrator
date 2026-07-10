"""任务调度器"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed

from src.core.worker import Worker
from src.models.schemas import Task, TaskPlan, TaskResult


class Dispatcher:
    """按任务依赖图（DAG）调度多个 Worker"""

    def __init__(self, worker: Worker, max_workers: int = 4):
        self.worker = worker
        self.max_workers = max_workers

    def dispatch(self, plan: TaskPlan, output_dir: str = "output") -> list[TaskResult]:
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

        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(plan.tasks))) as executor:
            futures: dict = {}

            # 提交初始无依赖任务
            for task_id in list(remaining):
                if is_ready(task_id):
                    remaining.remove(task_id)
                    future = executor.submit(self.worker.execute, tasks[task_id], output_dir)
                    futures[future] = task_id

            while futures:
                future = next(as_completed(futures))
                task_id = futures.pop(future)
                result = future.result()
                results.append(result)
                completed[task_id] = result

                status = "✅" if result.success else "❌"
                print(f"[{status}] {tasks[task_id].type}: {tasks[task_id].title}")
                if not result.success:
                    print(f"    错误: {result.error}")
                    self._cascade_failure(task_id, tasks, remaining, completed, results)

                # 提交新就绪的任务
                for next_id in list(remaining):
                    if is_ready(next_id):
                        remaining.remove(next_id)
                        futures[executor.submit(self.worker.execute, tasks[next_id], output_dir)] = next_id

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
            print(f"[❌] {tasks[task_id].type}: {tasks[task_id].title}")
            print(f"    错误: {result.error}")

        # 按任务 id 排序返回
        results.sort(key=lambda r: r.task.id)
        return results

    def _cascade_failure(
        self,
        failed_id: str,
        tasks: dict[str, Task],
        remaining: set[str],
        completed: dict[str, TaskResult],
        results: list[TaskResult],
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
                    queue.append(task_id)
                    print(f"[❌] {tasks[task_id].type}: {tasks[task_id].title}")
                    print(f"    错误: {result.error}")
