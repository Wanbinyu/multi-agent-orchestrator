"""Manual paid-model release smoke for two read-only Workers.

This script consumes Provider quota and is intentionally excluded from CI.
Its JSON evidence contains only aggregate metrics and synthetic marker checks.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from dotenv import load_dotenv

from src.core.dispatcher import Dispatcher
from src.core.worker import Worker, load_workers_config
from src.gateway.client import GatewayClient
from src.models.schemas import Task, TaskPlan


def run_smoke(
    config_dir: str = "config",
    first_model: str = "glm-ark",
    second_model: str = "kimi-for-coding",
) -> dict[str, object]:
    load_dotenv(override=True)
    gateway = GatewayClient(str(Path(config_dir) / "providers.yaml"))
    worker = Worker(
        gateway,
        load_workers_config(str(Path(config_dir) / "workers.yaml")),
        max_tool_iterations=2,
    )
    definitions = (
        ("glm-read", "continuity_checker", first_model, "GLM-READ-OK"),
        ("kimi-read", "frontend_dev", second_model, "KIMI-READ-OK"),
    )
    plan = TaskPlan(
        summary="release real two-model read-only smoke",
        tasks=[
            Task(
                id=task_id,
                type=worker_type,
                title=f"{model} read check",
                input=f"只返回字符串 {marker}，不调用工具。",
                output_format="纯文本",
                acceptance=f"结果包含 {marker}",
                assigned_model=model,
                execution_mode="read",
                parallel_safe=True,
                max_retries=0,
            )
            for task_id, worker_type, model, marker in definitions
        ],
    )
    with tempfile.TemporaryDirectory() as output:
        results = Dispatcher(worker, max_workers=2).dispatch(plan, output_dir=output)

    tasks = []
    for result, definition in zip(results, definitions):
        marker = definition[-1]
        isolated_artifacts = sum(
            Path(file_path).name in {"content.txt", "response.md"}
            for file_path in result.files_written
        )
        project_files_written = len(result.files_written) - isolated_artifacts
        tasks.append({
            "id": result.task.id,
            "model": result.task.assigned_model,
            "success": result.success,
            "attempts": result.attempts,
            "expected_marker_present": marker in result.content,
            "tool_calls": len(result.tool_calls),
            "isolated_artifacts": isolated_artifacts,
            "project_files_written": project_files_written,
            "input_tokens": result.response.input_tokens if result.response else 0,
            "output_tokens": result.response.output_tokens if result.response else 0,
            "cost_usd": result.response.cost_usd if result.response else 0,
            "error_category": "none" if not result.error else "worker_error",
        })
    return {
        "scenario": "real-two-model-read-only-collaboration",
        "tasks": tasks,
        "passed": (
            len(tasks) == 2
            and all(task["success"] for task in tasks)
            and all(task["expected_marker_present"] for task in tasks)
            and all(task["tool_calls"] == 0 for task in tasks)
            and all(task["project_files_written"] == 0 for task in tasks)
        ),
        "boundary": "read-only; no project writes",
        "automated_in_ci": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the paid two-model collaboration smoke")
    parser.add_argument("--config", default="config")
    parser.add_argument("--first-model", default="glm-ark")
    parser.add_argument("--second-model", default="kimi-for-coding")
    parser.add_argument("--output", default="docs/acceptance/real-collaboration-smoke.json")
    args = parser.parse_args()
    result = run_smoke(args.config, args.first_model, args.second_model)
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(rendered + "\n", encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
