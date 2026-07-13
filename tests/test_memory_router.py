"""记忆 Web API 路由测试"""
from __future__ import annotations

from fastapi.testclient import TestClient

from src.ui.app import app
from src.ui.routers import memory as memory_router

client = TestClient(app)


def _make_store(tmp_path):
    config_path = tmp_path / "config" / "memory.yaml"
    config_path.parent.mkdir(exist_ok=True)
    config_path.write_text(
        f"enabled: true\nstorage_path: {tmp_path / 'memory'}\n", encoding="utf-8"
    )
    from src.core.memory import MemoryStore

    return MemoryStore(config_path=str(config_path))


def test_memory_router_crud_flow(tmp_path):
    """测试记忆的完整 CRUD 搜索流程，使用独立存储目录"""
    store = _make_store(tmp_path)
    memory_router.memory_store = store

    # 创建
    resp = client.post(
        "/api/memory/entries",
        json={"category": "preference", "content": "用中文回复"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    entry_id = data["entry"]["id"]

    # 列出
    resp = client.get("/api/memory/entries")
    assert resp.status_code == 200
    assert len(resp.json()["entries"]) == 1

    # 搜索
    resp = client.post("/api/memory/search", json={"query": "中文", "top_k": 5})
    assert resp.status_code == 200
    assert any("中文" in e["content"] for e in resp.json()["entries"])

    # 删除
    resp = client.delete(f"/api/memory/entries/{entry_id}")
    assert resp.status_code == 200
    assert resp.json()["success"] is True

    resp = client.get("/api/memory/entries")
    assert len(resp.json()["entries"]) == 0


def test_memory_router_invalid_category(tmp_path):
    store = _make_store(tmp_path)
    memory_router.memory_store = store

    resp = client.post(
        "/api/memory/entries",
        json={"category": "invalid", "content": "内容"},
    )
    assert resp.status_code == 422


def test_memory_router_delete_not_found(tmp_path):
    store = _make_store(tmp_path)
    memory_router.memory_store = store

    resp = client.delete("/api/memory/entries/nonexistent")
    assert resp.status_code == 404


def test_memory_router_file_index_status(tmp_path):
    store = _make_store(tmp_path)
    memory_router.memory_store = store
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "store.py").write_text(
        "class SessionStore:\n    pass\n", encoding="utf-8"
    )

    # 未索引
    resp = client.get("/api/memory/files/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexed"] is False
    assert data["file_count"] == 0
    assert data["updated_at"] is None

    # 重建索引后
    resp = client.post("/api/memory/index", json={"root_dir": str(tmp_path), "force": True})
    assert resp.status_code == 200

    resp = client.get("/api/memory/files/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["indexed"] is True
    assert data["file_count"] == 1
    assert data["updated_at"] is not None


def test_memory_router_index_and_search_files(tmp_path):
    store = _make_store(tmp_path)
    memory_router.memory_store = store
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "store.py").write_text(
        "class SessionStore:\n    pass\n", encoding="utf-8"
    )

    resp = client.post("/api/memory/index", json={"root_dir": str(tmp_path), "force": True})
    assert resp.status_code == 200
    stats = resp.json()["stats"]
    assert stats["total"] == 1

    resp = client.post("/api/memory/files/search", json={"query": "SessionStore", "top_k": 5})
    assert resp.status_code == 200
    files = resp.json()["files"]
    assert len(files) == 1
    assert files[0]["path"] == "src/store.py"
    assert "SessionStore" in files[0]["symbols"]
