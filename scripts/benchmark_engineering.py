"""Run the public B5.1 engineering benchmark contract without Provider calls."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engineering import (  # noqa: E402
    EngineeringBenchmarkHarness,
    FixtureBenchmarkStrategy,
    BenchmarkStrategyProfile,
    write_benchmark_report,
)


def run_benchmark(
    output_root: str | Path,
    *,
    repeats: int = 3,
):
    suite = ROOT / "benchmarks" / "engineering_v1" / "suite.yaml"
    harness = EngineeringBenchmarkHarness(
        suite,
        output_root,
        [
            FixtureBenchmarkStrategy(
                "fixture-fixed-single",
                profile=BenchmarkStrategyProfile(
                    comparison_strategy="fixed-single",
                    routing_mode="fixed",
                    collaboration_mode="single",
                ),
            ),
            FixtureBenchmarkStrategy(
                "fixture-auto-route",
                profile=BenchmarkStrategyProfile(
                    comparison_strategy="auto-route",
                    routing_mode="auto",
                    collaboration_mode="single",
                ),
            ),
            FixtureBenchmarkStrategy(
                "fixture-multi-model",
                profile=BenchmarkStrategyProfile(
                    comparison_strategy="multi-model",
                    routing_mode="auto",
                    collaboration_mode="multi",
                ),
            ),
        ],
    )
    return harness.run(repeats=repeats, require_zero_provider_calls=True)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", help="Directory for isolated task workspaces")
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--json", dest="json_path", help="Optional JSON report path")
    parser.add_argument("--markdown", help="Optional Markdown report path")
    args = parser.parse_args()
    temporary = tempfile.TemporaryDirectory(prefix="mao-b5-benchmark-") if not args.workspace else None
    output_root = Path(args.workspace or temporary.name)
    try:
        report = run_benchmark(output_root, repeats=args.repeats)
        write_benchmark_report(
            report, json_path=args.json_path, markdown_path=args.markdown
        )
        print(json.dumps(report.model_dump(), ensure_ascii=False, indent=2))
        return 0 if report.passed else 1
    finally:
        if temporary is not None:
            temporary.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
