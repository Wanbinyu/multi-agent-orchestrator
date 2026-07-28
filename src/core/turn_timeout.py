"""Wall-clock deadlines for a single Agent turn."""
from __future__ import annotations

import os
import time
from dataclasses import dataclass


DEFAULT_TURN_TIMEOUT_SECONDS = 900.0  # 15 minutes; 0 disables


class TurnTimeoutError(TimeoutError):
    """Raised when an agent turn exceeds MAO_TURN_TIMEOUT_SECONDS."""

    def __init__(self, *, limit_seconds: float, elapsed_seconds: float):
        self.limit_seconds = limit_seconds
        self.elapsed_seconds = elapsed_seconds
        super().__init__(
            f"本轮对话已超过墙钟上限 {limit_seconds:.0f}s"
            f"（已运行 {elapsed_seconds:.0f}s）；"
            "可用环境变量 MAO_TURN_TIMEOUT_SECONDS 调整，0 表示关闭。"
        )


def resolve_turn_timeout_seconds(
    explicit: float | None = None,
    *,
    default: float = DEFAULT_TURN_TIMEOUT_SECONDS,
) -> float:
    """Return timeout seconds; 0 or negative means disabled."""
    if explicit is not None:
        return max(0.0, float(explicit))
    raw = os.environ.get("MAO_TURN_TIMEOUT_SECONDS")
    if raw is None or raw.strip() == "":
        return max(0.0, float(default))
    try:
        return max(0.0, float(raw))
    except ValueError:
        return max(0.0, float(default))


@dataclass
class TurnDeadline:
    """Monotonic deadline tracker for one turn."""

    limit_seconds: float
    started_at: float

    @classmethod
    def start(cls, limit_seconds: float | None = None) -> "TurnDeadline":
        limit = resolve_turn_timeout_seconds(limit_seconds)
        return cls(limit_seconds=limit, started_at=time.monotonic())

    @property
    def enabled(self) -> bool:
        return self.limit_seconds > 0

    def elapsed(self) -> float:
        return max(0.0, time.monotonic() - self.started_at)

    def remaining(self) -> float | None:
        if not self.enabled:
            return None
        return max(0.0, self.limit_seconds - self.elapsed())

    def check(self) -> None:
        if not self.enabled:
            return
        elapsed = self.elapsed()
        if elapsed >= self.limit_seconds:
            raise TurnTimeoutError(
                limit_seconds=self.limit_seconds,
                elapsed_seconds=elapsed,
            )
