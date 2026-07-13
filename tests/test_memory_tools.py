"""记忆相关工具单元测试"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.memory import MemoryStore, ProjectIndexer
from src.tools.memory_tools import search_memory, search_project_files
from src.tools.tool_result import ToolResult


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    config_path = tmp_path / "memory_config.yaml"
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    return MemoryStore(config_path=str(config_path))


def test_search_memory_empty_query():
    result = search_memory("   ")
    assert isinstance(result, ToolResult)
    assert result.success is False
    assert "查询词不能为空" in result.error


def test_search_memory_no_match(memory_store: MemoryStore):
    memory_store.add(category="preference", content="中文")
    result = search_memory("PostgreSQL")
    assert result.success is True
    assert "未找到" in result.output


def test_search_memory_returns_results(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    config_path = tmp_path / "config" / "memory.yaml"
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    store = MemoryStore(config_path=str(config_path))
    store.add(category="decision", content="使用 FastAPI")
    result = search_memory("FastAPI")
    assert result.success is True
    assert "使用 FastAPI" in result.output
    assert "decision" in result.output


def test_search_project_files_auto_index(memory_store: MemoryStore, tmp_path: Path):
    indexer = ProjectIndexer(memory_store)
    (tmp_path / "utils.py").write_text(
        "def helper():\n    return 42\n", encoding="utf-8"
    )
    indexer.index_project(root_dir=tmp_path, force=True)

    result = search_project_files("helper", base_dir=str(tmp_path))
    assert result.success is True
    assert "utils.py" in result.output


def test_search_project_files_empty_index(tmp_path, monkeypatch):
    # 空索引时自动触发一次索引构建
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config").mkdir()
    config_path = tmp_path / "config" / "memory.yaml"
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    (tmp_path / "api.py").write_text(
        "class Router:\n    pass\n", encoding="utf-8"
    )
    result = search_project_files("Router", base_dir=str(tmp_path))
    assert result.success is True
    assert "api.py" in result.output


def test_search_project_files_no_match(memory_store: MemoryStore, tmp_path: Path):
    indexer = ProjectIndexer(memory_store)
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")
    indexer.index_project(root_dir=tmp_path, force=True)

    result = search_project_files("nonexistent_symbol", base_dir=str(tmp_path))
    assert result.success is True
    assert "未找到" in result.output
