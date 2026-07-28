"""U4: 结构化 JSON/JSONL 运行事件写入器。

为 ``mao run --output-format json|streaming-json`` 提供稳定的事件流。

- ``streaming-json``：每个事件立即写一行 JSON（JSONL）。
- ``json``：事件收集到内存，``finish`` 时输出单个 JSON 对象 ``{"run": ..., "events": [...]}``。
- ``plain``：no-op，显示仍走现有 rich console。

事件信封：``{"type": <str>, "ts": <iso8601>, "run_id": <str>, "data": <dict>}``。
``end`` 必须最后：发出 ``end`` 后再 ``emit`` 会被丢弃；``finish`` 后 likewise。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any, TextIO
from uuid import uuid4

OutputFormat = str  # "plain" | "json" | "streaming-json"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class RunEventWriter:
    """按格式写入运行事件。

    Dispatcher 会从多个 Worker 线程调用进度回调，因此写入和事件收集必须
    在同一把锁内完成，避免 JSONL 行交叉或 JSON 事件丢失。
    """

    def __init__(
        self,
        fmt: OutputFormat = "plain",
        out: TextIO | None = None,
        run_id: str | None = None,
    ) -> None:
        if fmt not in ("plain", "json", "streaming-json"):
            raise ValueError(f"未知 output-format：{fmt!r}")
        self.fmt = fmt
        self._out = out or sys.stdout
        self._events: list[dict[str, Any]] = []
        self.run_id = (run_id or uuid4().hex).strip()
        if not self.run_id:
            raise ValueError("run_id 不能为空")
        self._ended = False
        self._finished = False
        self._start = time.perf_counter()
        self._lock = threading.Lock()

    def emit(self, event_type: str, data: dict[str, Any] | None = None) -> None:
        """发一个事件。``end`` 后或 ``finish`` 后调用被静默丢弃。"""
        with self._lock:
            if self._finished or self._ended:
                return
            envelope = {
                "type": event_type,
                "ts": _now_iso(),
                "run_id": self.run_id,
                "data": data or {},
            }
            if event_type == "end":
                self._ended = True
            if self.fmt == "streaming-json":
                self._out.write(json.dumps(envelope, ensure_ascii=False) + "\n")
                self._out.flush()
            elif self.fmt == "json":
                self._events.append(envelope)
            # plain: no-op

    def finish(self, summary: dict[str, Any] | None = None) -> None:
        """``json`` 模式输出最终单对象；其他模式 no-op。可重入安全。"""
        with self._lock:
            if self._finished:
                return
            self._finished = True
            if self.fmt == "json":
                payload = {"run": summary or {}, "events": self._events}
                self._out.write(json.dumps(payload, ensure_ascii=False) + "\n")
                self._out.flush()

    @property
    def finished(self) -> bool:
        return self._finished

    @property
    def ended(self) -> bool:
        return self._ended

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self._start) * 1000)


def build_usage(billing_summary: dict[str, Any]) -> dict[str, Any]:
    """从 ``GatewayClient.billing.summary()`` 构造 usage 事件 data。

    - ``usage_is_incomplete``：有调用但某条 input/output token 均为 0。
    - ``cost_is_partial``：有调用但某条 cost 为 0（价格未知）。
    - 缺失成本不为零：全部未知时 ``total_cost_usd`` 为 ``None``。
    - ``by_model`` / ``by_role``：按 model / task_id 聚合，多模型分别统计。
    """
    calls = list(billing_summary.get("calls") or [])
    total_in = int(billing_summary.get("total_input_tokens", 0) or 0)
    total_out = int(billing_summary.get("total_output_tokens", 0) or 0)
    total_cost = float(billing_summary.get("total_cost_usd", 0.0) or 0.0)
    usage_is_incomplete = bool(calls) and any(
        (c.get("input_tokens", 0) or 0) == 0 and (c.get("output_tokens", 0) or 0) == 0
        for c in calls
    )
    cost_is_partial = bool(calls) and any((c.get("cost_usd", 0.0) or 0.0) == 0.0 for c in calls)
    total_cost_usd: float | None = round(total_cost, 6)
    if total_cost_usd == 0.0 and cost_is_partial:
        total_cost_usd = None  # 全部未知，不展示为零
    return {
        "total_input_tokens": total_in,
        "total_output_tokens": total_out,
        "total_cost_usd": total_cost_usd,
        "usage_is_incomplete": usage_is_incomplete,
        "cost_is_partial": cost_is_partial,
        "by_model": _aggregate(calls, "model"),
        "by_role": _aggregate(calls, "task_id"),
    }


def _aggregate(calls: list[dict[str, Any]], key: str) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for c in calls:
        k = str(c.get(key) or "unknown")
        b = buckets.setdefault(
            k,
            {
                "key": k,
                "calls": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "cost_known": True,
            },
        )
        b["calls"] += 1
        b["input_tokens"] += int(c.get("input_tokens", 0) or 0)
        b["output_tokens"] += int(c.get("output_tokens", 0) or 0)
        cost = float(c.get("cost_usd", 0.0) or 0.0)
        b["cost_usd"] += cost
        if cost == 0.0:
            b["cost_known"] = False
    for b in buckets.values():
        b["cost_usd"] = round(b["cost_usd"], 6)
    return list(buckets.values())
