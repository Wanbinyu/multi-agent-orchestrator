"""Run one explicitly authorized B5.4 live three-strategy smoke."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engineering import (  # noqa: E402
    BenchmarkStrategyProfile,
    EngineeringBenchmarkHarness,
    LiveBenchmarkAuthorization,
    LiveBenchmarkSpendGuard,
    MaoLiveBenchmarkStrategy,
    write_benchmark_report,
)


def main() -> int:
    load_dotenv(ROOT / ".env", override=False)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-live-provider", action="store_true")
    parser.add_argument("--main-model", required=True)
    parser.add_argument("--allowed-model", action="append", dest="allowed_models", required=True)
    parser.add_argument("--task-id", default="build-health-module")
    parser.add_argument(
        "--strategy",
        action="append",
        choices=["fixed-single", "auto-route", "multi-model"],
        dest="selected_strategies",
        help="Strategy to run; repeatable. Defaults to all three.",
    )
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--max-provider-calls", type=int, required=True)
    parser.add_argument("--stop-after-cost-usd", type=float, required=True)
    parser.add_argument(
        "--result-visibility",
        choices=["private", "aggregate", "full"],
        default="private",
    )
    parser.add_argument("--config", default="config")
    parser.add_argument("--output-root", default="sessions/benchmarks/b5.4-live-smoke")
    args = parser.parse_args()
    if not args.confirm_live_provider:
        parser.error("must pass --confirm-live-provider after owner authorization")
    allowed_models = list(dict.fromkeys(args.allowed_models))
    if len(allowed_models) < 2:
        parser.error("live comparison requires at least two --allowed-model values")
    if args.main_model not in allowed_models:
        parser.error("--main-model must also be listed in --allowed-model")

    root = Path(args.output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    authorization = LiveBenchmarkAuthorization(
        confirmation_reference="owner-confirmed-in-current-session",
        allowed_models=allowed_models,
        max_provider_calls=args.max_provider_calls,
        stop_after_cost_usd=args.stop_after_cost_usd,
        result_visibility=args.result_visibility,
    )
    guard = LiveBenchmarkSpendGuard(authorization)
    profiles = [
        ("live-fixed-single", "fixed-single", "fixed", "single", [args.main_model]),
        ("live-auto-route", "auto-route", "auto", "single", allowed_models),
        ("live-multi-model", "multi-model", "auto", "multi", allowed_models),
    ]
    selected_strategies = set(
        args.selected_strategies or ["fixed-single", "auto-route", "multi-model"]
    )
    profiles = [
        profile for profile in profiles if profile[1] in selected_strategies
    ]
    strategies = [
        MaoLiveBenchmarkStrategy(
            strategy_id,
            profile=BenchmarkStrategyProfile(
                comparison_strategy=comparison_strategy,
                routing_mode=routing_mode,
                collaboration_mode=collaboration_mode,
                execution_depth="standard",
                configured_models=models,
            ),
            config_dir=args.config,
            state_root=root / "state",
            main_model=args.main_model,
            spend_guard=guard,
        )
        for strategy_id, comparison_strategy, routing_mode, collaboration_mode, models
        in profiles
    ]
    harness = EngineeringBenchmarkHarness(
        ROOT / "benchmarks" / "engineering_v1" / "suite.yaml",
        root / "workspaces",
        strategies,
    )
    report = harness.run(
        repeats=args.repeats,
        task_ids=[args.task_id],
        require_zero_provider_calls=False,
        require_stable_results=False,
        fail_fast=True,
    )
    report_dir = root / "reports"
    json_path = report_dir / f"{report.run_id}.json"
    markdown_path = report_dir / f"{report.run_id}.md"
    write_benchmark_report(report, json_path=json_path, markdown_path=markdown_path)
    summary = {
        "run_id": report.run_id,
        "passed": report.passed,
        "task_ids": report.selected_task_ids,
        "provider_calls": guard.provider_calls,
        "provider_attempts": guard.provider_attempts,
        "cost_usd": guard.cost_usd,
        "result_visibility": authorization.result_visibility,
        "report_json": str(json_path),
        "report_markdown": str(markdown_path),
        "strategies": [
            {
                "strategy": item.strategy_id,
                "passed": item.passed,
                "internal_status": item.internal_status,
                "actual_models": item.actual_models,
                "upstream_model_ids": item.upstream_model_ids,
                "tokens": [item.input_tokens, item.output_tokens],
                "cost_usd": item.cost_usd,
                "issues": item.issues,
            }
            for item in report.results
        ],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if report.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
