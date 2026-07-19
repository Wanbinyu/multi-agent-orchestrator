"""Run the public smart-mining stability release gate without Provider calls."""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.core.engineering import StabilityReplayRunner  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    fixture = ROOT / "tests" / "fixtures" / "smart_mining"
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="mao-smart-mining-replay-") as temp:
        base = Path(temp)
        for mode in ("good", "broken_mock", "missing_route"):
            outcomes.append(
                StabilityReplayRunner(fixture, base / mode).run(mode)  # type: ignore[arg-type]
            )
    payload = {item.mode: item.model_dump() for item in outcomes}
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    good = payload["good"]
    failures_blocked = all(
        not payload[mode]["passed"] and payload[mode]["status"] == "blocked"
        for mode in ("broken_mock", "missing_route")
    )
    no_provider_calls = all(item.provider_calls == 0 for item in outcomes)
    return 0 if good["passed"] and failures_blocked and no_provider_calls else 1


if __name__ == "__main__":
    raise SystemExit(main())
