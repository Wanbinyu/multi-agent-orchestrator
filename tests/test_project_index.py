"""B4.5 persistent hash index and cross-turn reconnaissance reuse."""
from __future__ import annotations

import os
from pathlib import Path

from src.core.memory import MemoryStore, ProjectIndexer
from src.tools.memory_tools import search_project_files
from src.tools.search_tools import project_tree
from src.tools.registry import tool_registry


def _store(tmp_path: Path) -> MemoryStore:
    config = tmp_path / "config" / "memory.yaml"
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'cache'}\n",
        encoding="utf-8",
    )
    return MemoryStore(str(config))


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text(
        "class Application:\n    pass\n", encoding="utf-8"
    )
    (root / "README.md").write_text("# Indexed project\n", encoding="utf-8")
    return root


def test_unchanged_second_refresh_reads_zero_file_contents(tmp_path):
    store = _store(tmp_path)
    root = _project(tmp_path)
    indexer = ProjectIndexer(store)

    first = indexer.index_project(root)
    second = indexer.index_project(root)

    assert first["read"] == 2
    assert first["added"] == 2
    assert second["read"] == 0
    assert second["reused"] == 2
    assert second["added"] == second["updated"] == 0
    assert all(entry.content_hash for entry in store.get_file_index().files.values())


def test_registry_runtime_memory_store_keeps_index_outside_target_project(tmp_path):
    store = _store(tmp_path)
    root = _project(tmp_path)

    result = tool_registry.execute(
        "project_tree",
        {"path": str(root)},
        base_dir=str(root),
        runtime_context={"memory_store": store},
    )

    assert result.success is True
    assert store.file_index_path.is_file()
    assert not (root / "config" / "memory" / "file_index.yaml").exists()
    assert store.get_file_index().root == str(root.resolve())
    assert "src/app.py" in store.get_file_index().tree_paths
    assert "src" in store.get_file_index().directories


def test_excluded_directories_are_case_insensitive(tmp_path):
    store = _store(tmp_path)
    root = _project(tmp_path)
    excluded = root / "Node_Modules"
    excluded.mkdir()
    (excluded / "package.js").write_text("secret dependency", encoding="utf-8")

    stats = ProjectIndexer(store).index_project(root)

    assert stats["total"] == 2
    assert not any("Node_Modules" in path for path in store.get_file_index().tree_paths)


def test_single_file_change_reads_and_rebuilds_only_that_entry(tmp_path):
    store = _store(tmp_path)
    root = _project(tmp_path)
    indexer = ProjectIndexer(store)
    indexer.index_project(root)
    old_hash = store.get_file_index().files["src/app.py"].content_hash
    (root / "src" / "app.py").write_text(
        "class ApplicationV2:\n    enabled = True\n", encoding="utf-8"
    )

    stats = indexer.index_project(root)

    assert stats["read"] == 1
    assert stats["updated"] == 1
    assert stats["reused"] == 1
    entry = store.get_file_index().files["src/app.py"]
    assert entry.content_hash != old_hash
    assert "ApplicationV2" in entry.symbols


def test_metadata_change_with_same_hash_reuses_parsed_summary(tmp_path):
    store = _store(tmp_path)
    root = _project(tmp_path)
    indexer = ProjectIndexer(store)
    indexer.index_project(root)
    path = root / "README.md"
    original = store.get_file_index().files["README.md"]
    os.utime(path, (original.mtime + 5, original.mtime + 5))

    stats = indexer.index_project(root)

    assert stats["read"] == 1
    assert stats["metadata_only"] == 1
    assert stats["updated"] == 0
    refreshed = store.get_file_index().files["README.md"]
    assert refreshed.content_hash == original.content_hash
    assert refreshed.summary == original.summary


def test_removed_file_is_dropped_without_rereading_unchanged_file(tmp_path):
    store = _store(tmp_path)
    root = _project(tmp_path)
    indexer = ProjectIndexer(store)
    indexer.index_project(root)
    (root / "README.md").unlink()

    stats = indexer.index_project(root)

    assert stats["removed"] == 1
    assert stats["read"] == 0
    assert set(store.get_file_index().files) == {"src/app.py"}


def test_corrupt_index_falls_back_to_full_refresh(tmp_path):
    store = _store(tmp_path)
    root = _project(tmp_path)
    ProjectIndexer(store).index_project(root)
    store.file_index_path.write_text("files: [broken", encoding="utf-8")
    recovered_store = MemoryStore(str(store.config_path))

    stats = ProjectIndexer(recovered_store).index_project(root)

    assert stats["cache_recovered"] is True
    assert stats["read"] == 2
    assert stats["total"] == 2
    assert recovered_store.file_index_load_failed is False


def test_project_tree_and_search_refresh_index_without_cross_root_leak(tmp_path):
    store = _store(tmp_path)
    first_root = _project(tmp_path)
    first_tree = project_tree(str(first_root), memory_store=store)
    second_tree = project_tree(str(first_root), memory_store=store)

    assert first_tree.success is True
    assert first_tree.metadata["cached"] is False
    assert second_tree.metadata["cached"] is True
    assert second_tree.metadata["project_index"]["read"] == 0
    assert "Application" not in second_tree.output  # tree uses paths, not file contents
    assert "app.py" in second_tree.output

    second_root = tmp_path / "other"
    second_root.mkdir()
    (second_root / "beta.py").write_text(
        "class BetaSymbol:\n    pass\n", encoding="utf-8"
    )
    result = search_project_files(
        "BetaSymbol", base_dir=str(second_root), memory_store=store
    )

    assert result.success is True
    assert "beta.py" in result.output
    assert "app.py" not in result.output
    assert result.metadata["project_index"]["root_changed"] is True
