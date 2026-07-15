from scripts.context_benchmark import run_benchmark


def test_minimum_offline_long_session_benchmark(tmp_path):
    result = run_benchmark(str(tmp_path))
    assert result["passed"] is True
    assert result["provider_calls"] == 0
    assert result["compactions"] == 1
    assert result["session_recovered"] is True
    assert result["critical_fact_retention"] == 1.0
