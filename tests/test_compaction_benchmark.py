"""Fast contract for the B4.4 offline benchmark."""
from scripts.bench_compaction import run_benchmark


def test_layered_compaction_benchmark_single_profile(tmp_path):
    result = run_benchmark(str(tmp_path), profiles=(32_000,))

    assert result["passed"] is True
    assert result["provider_calls"] == 0
    profile = result["profiles"][0]
    assert profile["compactions"] == 3
    assert profile["critical_fact_retention"] == 1.0
    assert profile["final_layers"] == ["L0", "L1", "L2"]
    assert profile["task_relevance_ratio"] > 0
