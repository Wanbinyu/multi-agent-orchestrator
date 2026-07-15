"""单轮只读工具缓存规则测试。"""
from src.tools.read_cache import build_read_cache_key, should_invalidate_read_cache


def test_cache_key_is_stable_for_parameter_order(tmp_path):
    first = build_read_cache_key(
        "project_tree", {"path": ".", "max_depth": 4}, str(tmp_path)
    )
    second = build_read_cache_key(
        "project_tree", {"max_depth": 4, "path": "."}, str(tmp_path)
    )
    assert first == second


def test_only_read_tools_receive_cache_keys(tmp_path):
    assert build_read_cache_key("read_file", {"path": "a.py"}, str(tmp_path))
    assert build_read_cache_key("write_file", {"path": "a.py"}, str(tmp_path)) is None


def test_mutating_and_unknown_tools_invalidate_cache():
    assert should_invalidate_read_cache("write_file") is True
    assert should_invalidate_read_cache("edit_file") is True
    assert should_invalidate_read_cache("run_command") is True
    assert should_invalidate_read_cache("unknown_external_tool") is True
    assert should_invalidate_read_cache("web_search") is False
    assert should_invalidate_read_cache("read_file") is False
