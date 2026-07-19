"""Offline B4.4 layered-compaction benchmark for four context profiles."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Iterable

from src.core.compactor import ContextCompactor
from src.core.token_counter import count_message_tokens, count_messages_tokens, count_tokens
from src.models.schemas import ChatMessage


WINDOW_PROFILES = (32_000, 64_000, 128_000, 200_000)
CRITICAL_FACTS = (
    "KEEP:requirement=preserve-explicit-write-boundaries",
    "KEEP:file=src/core/compactor.py",
    "KEEP:todo=finish-beta4-release-gates",
    "20260718-120000-123456-b4bench",
)


class _OfflineStructuredSummaryGateway:
    main_model = "offline-deterministic-structured-summary"

    def __init__(self):
        self.summary_calls = 0

    def chat_with_main_model(self, messages=None, **_kwargs):
        self.summary_calls += 1
        transcript = messages[-1].content if messages else ""
        retained = [fact for fact in CRITICAL_FACTS if fact in transcript]
        return SimpleNamespace(content=json.dumps({
            "schema_version": 1,
            "requirements": [item for item in retained if "requirement=" in item],
            "decisions": [],
            "evidence": retained,
            "files_changed": ["src/core/compactor.py"] if "compactor.py" in transcript else [],
            "todos": [item for item in retained if "todo=" in item],
            "risks": [],
            "run_refs": [item for item in retained if item.startswith("2026")],
            "output_files": [],
        }, ensure_ascii=False))


def _append_until(
    messages: list[ChatMessage], target_tokens: int, round_id: int
) -> None:
    current = count_messages_tokens(messages)
    index = 0
    while current <= target_tokens or len(messages) < 12:
        message = ChatMessage(
            role="user" if index % 2 == 0 else "assistant",
            content=(
                f"profile-noise-round-{round_id}-{index}:"
                + chr(97 + (index % 26)) * 6000
            ),
        )
        messages.append(message)
        current += count_message_tokens(message)
        index += 1


def _run_profile(window: int, root: Path) -> dict[str, object]:
    gateway = _OfflineStructuredSummaryGateway()
    messages = [
        ChatMessage(role="system", content="MAO B4.4 offline benchmark"),
        ChatMessage(role="user", content=" ".join(CRITICAL_FACTS)),
        ChatMessage(role="assistant", content="critical facts acknowledged"),
        ChatMessage(role="user", content="[MAO_TASK_CHECKPOINT] B4.4 benchmark active"),
    ]
    compactor = ContextCompactor(
        gateway,
        max_context_tokens=window,
        threshold=0.72,
        keep_recent=6,
        min_messages_to_compact=10,
        artifact_dir=root / str(window) / "context",
    )
    rounds: list[dict[str, object]] = []
    for round_id in range(3):
        _append_until(messages, compactor.compact_limit + 512, round_id)
        before = count_messages_tokens(messages)
        compacted = compactor.maybe_compact(messages)
        after = count_messages_tokens(compacted)
        rounds.append({
            "round": round_id + 1,
            "tokens_before": before,
            "tokens_after": after,
            "reduction_ratio": round(1 - after / before, 4),
            "metadata": compactor.last_metadata.model_dump(),
        })
        messages = compacted

    final_text = "\n".join(message.content for message in messages)
    retained = [fact for fact in CRITICAL_FACTS if fact in final_text]
    relevant_tokens = sum(count_tokens(fact) for fact in retained)
    final_tokens = count_messages_tokens(messages)
    relevance = relevant_tokens / max(1, final_tokens)
    layers = compactor.last_metadata.layers
    artifact_paths = list((root / str(window) / "context").glob("compaction-*.json"))
    passed = (
        len(rounds) == 3
        and all(item["tokens_after"] < item["tokens_before"] for item in rounds)
        and len(retained) == len(CRITICAL_FACTS)
        and layers == ["L0", "L1", "L2"]
        and bool(artifact_paths)
        and compactor.last_metadata.quality_passed
        and relevance > 0
    )
    return {
        "window_tokens": window,
        "passed": passed,
        "provider_calls": 0,
        "offline_summary_calls": gateway.summary_calls,
        "compactions": len(rounds),
        "critical_fact_retention": len(retained) / len(CRITICAL_FACTS),
        "task_relevance_ratio": round(relevance, 6),
        "final_tokens": final_tokens,
        "final_layers": layers,
        "artifact_count": len(artifact_paths),
        "rounds": rounds,
    }


def run_benchmark(
    base_dir: str | None = None,
    profiles: Iterable[int] = WINDOW_PROFILES,
) -> dict[str, object]:
    started = time.perf_counter()
    temporary = tempfile.TemporaryDirectory() if base_dir is None else None
    root = Path(base_dir or temporary.name)
    results = [_run_profile(int(window), root) for window in profiles]
    output: dict[str, object] = {
        "benchmark": "b4-layered-context-compaction",
        "provider_calls": 0,
        "profiles": results,
        "passed": bool(results) and all(item["passed"] for item in results),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
    }
    if temporary is not None:
        temporary.cleanup()
    return output


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", help="Optional JSON evidence path")
    args = parser.parse_args()
    result = run_benchmark()
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rendered + "\n", encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
