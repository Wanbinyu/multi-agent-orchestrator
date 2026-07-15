"""Offline minimum long-session release benchmark.

No Provider request is made. A deterministic summarizer retains explicitly marked
facts so the benchmark measures compaction, large-output handling and session
recovery without spending tokens or pretending to validate model summary quality.
"""
from __future__ import annotations

import argparse
import json
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

from src.core.compactor import ContextCompactor
from src.core.session import SessionStore
from src.core.token_counter import count_messages_tokens


CRITICAL_FACTS = (
    "KEEP:requirement=preserve-explicit-write-boundaries",
    "KEEP:file=src/core/context_budget.py",
    "KEEP:todo=run-release-smoke",
)


class _OfflineSummaryGateway:
    main_model = "offline-deterministic-summary"

    def chat_with_main_model(self, messages, **_kwargs):
        transcript = messages[-1].content
        retained = [fact for fact in CRITICAL_FACTS if fact in transcript]
        return SimpleNamespace(content="\n".join(retained))


def run_benchmark(base_dir: str | None = None) -> dict[str, object]:
    started = time.perf_counter()
    temp = tempfile.TemporaryDirectory() if base_dir is None else None
    root = Path(base_dir or temp.name)
    store = SessionStore(str(root / "sessions"))
    session = store.create("offline-context-release-benchmark")
    session.add_message("system", "MAO offline benchmark")
    for fact in CRITICAL_FACTS:
        session.add_message("user", fact)
        session.add_message("assistant", "ack")
    for index in range(16):
        session.add_message("user", f"tool-result-{index}:" + "x" * 1800)
        session.add_message("assistant", f"processed-{index}")

    before_tokens = count_messages_tokens(session.messages)
    compactor = ContextCompactor(
        _OfflineSummaryGateway(),
        max_context_tokens=5_000,
        threshold=0.6,
        keep_recent=6,
        min_messages_to_compact=10,
    )
    compacted = compactor.maybe_compact(session.messages)
    after_tokens = count_messages_tokens(compacted)
    session.messages = compacted
    store.save(session)
    recovered = store.load(session.id)
    recovered_text = "\n".join(message.content for message in recovered.messages)
    retained = [fact for fact in CRITICAL_FACTS if fact in recovered_text]

    result: dict[str, object] = {
        "benchmark": "minimum-offline-long-session",
        "provider_calls": 0,
        "messages_before": 1 + len(CRITICAL_FACTS) * 2 + 16 * 2,
        "messages_after": len(compacted),
        "tokens_before": before_tokens,
        "tokens_after": after_tokens,
        "compactions": 1 if len(compacted) < 39 else 0,
        "session_recovered": recovered.id == session.id,
        "critical_facts_total": len(CRITICAL_FACTS),
        "critical_facts_retained": len(retained),
        "critical_fact_retention": len(retained) / len(CRITICAL_FACTS),
        "passed": (
            len(compacted) < 39
            and after_tokens < before_tokens
            and recovered.id == session.id
            and len(retained) == len(CRITICAL_FACTS)
        ),
        "elapsed_ms": round((time.perf_counter() - started) * 1000, 2),
        "limitations": [
            "Uses a deterministic offline summarizer; real model summary quality requires manual smoke testing.",
            "Covers one compaction and recovery, not the post-beta three-compaction benchmark.",
        ],
    }
    if temp is not None:
        temp.cleanup()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run MAO's offline context release benchmark")
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
