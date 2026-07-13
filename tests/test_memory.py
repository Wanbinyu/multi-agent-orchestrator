"""MemoryStore、MemoryContextBuilder、ProjectIndexer 单元测试"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.core.memory import (
    MemoryConfig,
    MemoryContextBuilder,
    MemoryEntry,
    MemoryStore,
    ProjectIndexer,
    tokenize,
)


@pytest.fixture
def memory_store(tmp_path: Path) -> MemoryStore:
    """在临时目录中创建独立 MemoryStore"""
    config_path = tmp_path / "memory.yaml"
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    return MemoryStore(config_path=str(config_path))


def test_tokenize_english_and_chinese():
    assert tokenize("Hello world 你好世界") == ["hello", "world", "你", "好", "世", "界"]
    assert tokenize("") == []
    assert tokenize("_private_var 123") == ["_private_var"]


def test_memory_entry_defaults():
    entry = MemoryEntry(category="preference", content="  用中文回复  ")
    assert entry.content == "用中文回复"
    assert len(entry.id) == 12
    assert entry.importance == 3


def test_memory_store_add_and_get(memory_store: MemoryStore):
    entry = memory_store.add(category="preference", content="用中文回复", tags=["lang"])
    fetched = memory_store.get(entry.id)
    assert fetched is not None
    assert fetched.category == "preference"
    assert fetched.content == "用中文回复"
    assert fetched.tags == ["lang"]


def test_memory_store_delete(memory_store: MemoryStore):
    entry = memory_store.add(category="fact", content="项目使用 FastAPI")
    assert memory_store.delete(entry.id) is True
    assert memory_store.get(entry.id) is None
    assert memory_store.delete("nonexistent") is False


def test_memory_store_list_filter(memory_store: MemoryStore):
    memory_store.add(category="preference", content="中文")
    memory_store.add(category="decision", content="FastAPI")
    memory_store.add(category="preference", content="简洁", tags=["style"])

    prefs = memory_store.list(category="preference")
    assert len(prefs) == 2
    assert all(e.category == "preference" for e in prefs)

    tagged = memory_store.list(tag="style")
    assert len(tagged) == 1
    assert tagged[0].content == "简洁"


def test_memory_store_search_ranking(memory_store: MemoryStore):
    memory_store.add(category="decision", content="项目使用 FastAPI 而不是 Flask")
    memory_store.add(category="preference", content="用户偏好中文回复")
    memory_store.add(category="fact", content="数据库使用 PostgreSQL")

    results = memory_store.search("FastAPI", top_k=5)
    assert len(results) == 1
    assert results[0].content == "项目使用 FastAPI 而不是 Flask"

    results = memory_store.search("中文", top_k=5)
    assert any("中文" in e.content for e in results)


def test_memory_context_builder_limits_chars(memory_store: MemoryStore):
    memory_store.add(category="preference", content="中文")
    memory_store.add(category="decision", content="使用 FastAPI")
    builder = MemoryContextBuilder(memory_store)

    context = builder.build_context("FastAPI", max_chars=200)
    assert "【项目记忆与上下文】" in context
    assert "【项目记忆结束】" in context
    assert len(context) <= 200


def test_memory_context_builder_disabled(memory_store: MemoryStore):
    memory_store.config.enabled = False
    memory_store.add(category="preference", content="中文")
    builder = MemoryContextBuilder(memory_store)
    assert builder.build_context("中文") == ""


def test_memory_store_persistence(tmp_path: Path):
    config_path = tmp_path / "memory.yaml"
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    store1 = MemoryStore(config_path=str(config_path))
    entry = store1.add(category="fact", content="持久化测试")

    store2 = MemoryStore(config_path=str(config_path))
    assert len(store2.list()) == 1
    assert store2.get(entry.id).content == "持久化测试"


def test_project_indexer_creates_index(memory_store: MemoryStore, tmp_path: Path):
    indexer = ProjectIndexer(memory_store)
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text("def main():\n    pass\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("# Test project\n", encoding="utf-8")

    stats = indexer.index_project(root_dir=tmp_path, force=True)
    assert stats["total"] == 2
    assert stats["added"] == 2

    files = memory_store.get_file_index().files
    assert "src/app.py" in files
    assert files["src/app.py"].symbols == ["main"]
    assert "README.md" in files


def test_project_indexer_excluded_dirs(memory_store: MemoryStore, tmp_path: Path):
    indexer = ProjectIndexer(memory_store)
    venv = tmp_path / "venv"
    venv.mkdir()
    (venv / "site.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("x = 1\n", encoding="utf-8")

    stats = indexer.index_project(root_dir=tmp_path, force=True)
    assert stats["total"] == 1
    assert "main.py" in memory_store.get_file_index().files


def test_project_indexer_incremental_update(memory_store: MemoryStore, tmp_path: Path):
    indexer = ProjectIndexer(memory_store)
    f = tmp_path / "module.py"
    f.write_text("def foo(): pass\n", encoding="utf-8")

    indexer.index_project(root_dir=tmp_path, force=True)
    first_mtime = memory_store.get_file_index().files["module.py"].mtime

    # 未变更再次索引应保留原条目
    stats = indexer.index_project(root_dir=tmp_path, force=False)
    assert stats["total"] == 1
    assert stats["added"] == 0
    assert stats["updated"] == 0
    assert memory_store.get_file_index().files["module.py"].mtime == first_mtime


def test_search_files(memory_store: MemoryStore, tmp_path: Path):
    indexer = ProjectIndexer(memory_store)
    (tmp_path / "store.py").write_text(
        "class SessionStore:\n    pass\n", encoding="utf-8"
    )
    indexer.index_project(root_dir=tmp_path, force=True)

    results = memory_store.search_files("SessionStore", top_k=5)
    assert len(results) == 1
    assert results[0].path == "store.py"
    assert "SessionStore" in results[0].symbols


def test_memory_config_defaults(tmp_path: Path):
    config_path = tmp_path / "missing.yaml"
    store = MemoryStore(config_path=str(config_path))
    assert isinstance(store.config, MemoryConfig)
    assert store.config.enabled is True
    assert ".py" in store.config.indexed_extensions
    assert "__pycache__" in store.config.excluded_dirs
