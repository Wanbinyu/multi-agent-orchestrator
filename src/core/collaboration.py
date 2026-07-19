"""多模型协作计划的边界、所有权和并行安全校验。"""
from __future__ import annotations

import ntpath
from pathlib import Path

from src.models.schemas import Task, TaskPlan


MAX_COLLABORATION_TASKS = 24


class CollaborationPlanError(ValueError):
    """协作计划违反确定性执行边界。"""


def normalize_task_contract(task: Task) -> Task:
    """为旧模型输出补齐最小可验收契约。"""
    if not task.output_format.strip():
        task.output_format = "给出结构化完成说明，并列出实际文件或验证结果"
    if not task.acceptance.strip():
        task.acceptance = "产出可检查的结果，失败时明确错误和未完成项"
    if task.type in {"tester", "test", "qa"}:
        task.execution_mode = "verify"
    elif task.type in {"continuity_checker", "reviewer", "analyst"}:
        task.execution_mode = "read"
    return task


def validate_collaboration_plan(plan: TaskPlan) -> None:
    """拒绝重复 ID、无效依赖、依赖环和并行文件所有权冲突。"""
    tasks = plan.tasks
    if len(tasks) > MAX_COLLABORATION_TASKS:
        raise CollaborationPlanError(
            f"协作计划包含 {len(tasks)} 个子任务，超过上限 {MAX_COLLABORATION_TASKS}"
        )
    ids = [task.id for task in tasks]
    duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
    if duplicates:
        raise CollaborationPlanError(f"子任务 ID 重复：{', '.join(duplicates)}")
    known = set(ids)
    for task in tasks:
        if task.id in task.depends_on:
            raise CollaborationPlanError(f"子任务 {task.id} 不能依赖自身")
        missing = [dep for dep in task.depends_on if dep not in known]
        if missing:
            raise CollaborationPlanError(
                f"子任务 {task.id} 引用了不存在的依赖：{', '.join(missing)}"
            )
    _assert_acyclic(tasks)
    conflicts = find_parallel_ownership_conflicts(plan)
    if conflicts:
        left, right, path = conflicts[0]
        raise CollaborationPlanError(
            f"并行子任务 {left} 与 {right} 的文件所有权冲突：{path}"
        )


def find_parallel_ownership_conflicts(
    plan: TaskPlan,
) -> list[tuple[str, str, str]]:
    tasks = plan.tasks
    conflicts: list[tuple[str, str, str]] = []
    for index, left in enumerate(tasks):
        if left.execution_mode == "read":
            continue
        for right in tasks[index + 1 :]:
            if right.execution_mode == "read":
                continue
            if _depends_on(left.id, right.id, tasks) or _depends_on(
                right.id, left.id, tasks
            ):
                continue
            for left_path in _absolute_owned_paths(left):
                for right_path in _absolute_owned_paths(right):
                    if _paths_overlap(left_path, right_path):
                        conflicts.append((left.id, right.id, left_path))
    return conflicts


def is_write_path_allowed(task: Task, raw_path: str, base_dir: str) -> bool:
    """相对写入只进隔离目录；共享绝对写入必须落在任务所有权内。"""
    target = Path(raw_path)
    if not target.is_absolute():
        resolved = (Path(base_dir).resolve() / target).resolve()
        try:
            resolved.relative_to(Path(base_dir).resolve())
            return True
        except ValueError:
            return False
    normalized_target = _normalize_absolute(str(target))
    return any(
        _path_contains(owner, normalized_target)
        for owner in _absolute_owned_paths(task)
    )


def _absolute_owned_paths(task: Task) -> list[str]:
    return [
        _normalize_absolute(path)
        for path in task.owned_paths
        if Path(path).is_absolute() or ntpath.isabs(path)
    ]


def _normalize_absolute(path: str) -> str:
    return ntpath.normcase(ntpath.normpath(path.replace("/", "\\")))


def _path_contains(owner: str, target: str) -> bool:
    if owner == target:
        return True
    return target.startswith(owner.rstrip("\\") + "\\")


def _paths_overlap(left: str, right: str) -> bool:
    return _path_contains(left, right) or _path_contains(right, left)


def _depends_on(task_id: str, dependency_id: str, tasks: list[Task]) -> bool:
    by_id = {task.id: task for task in tasks}
    queue = list(by_id[task_id].depends_on)
    seen: set[str] = set()
    while queue:
        current = queue.pop()
        if current == dependency_id:
            return True
        if current in seen or current not in by_id:
            continue
        seen.add(current)
        queue.extend(by_id[current].depends_on)
    return False


def _assert_acyclic(tasks: list[Task]) -> None:
    by_id = {task.id: task for task in tasks}
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(task_id: str) -> None:
        if task_id in visiting:
            raise CollaborationPlanError(f"协作计划存在依赖环：{task_id}")
        if task_id in visited:
            return
        visiting.add(task_id)
        for dependency in by_id[task_id].depends_on:
            visit(dependency)
        visiting.remove(task_id)
        visited.add(task_id)

    for task_id in by_id:
        visit(task_id)
