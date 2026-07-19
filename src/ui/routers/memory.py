"""记忆与项目文件索引 API 路由"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator

from src.core.memory import MemoryCategory, MemoryStore, ProjectIndexer
from src.core.session import SessionStore
from src.core.summarizer import SessionSummarizer
from src.gateway.client import GatewayClient

router = APIRouter()

# 复用同一个 MemoryStore 实例（FastAPI 同步路由内使用）
memory_store = MemoryStore()
session_store = SessionStore(base_dir="sessions")


class MemoryEntryOut(BaseModel):
    id: str
    category: str
    content: str
    source: str
    tags: list[str]
    importance: int
    created_at: str
    updated_at: str


class CreateMemoryForm(BaseModel):
    category: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    source: str = "api"
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)

    @field_validator("category")
    @classmethod
    def _check_category(cls, value: str) -> str:
        allowed = {
            "preference",
            "decision",
            "fact",
            "project_structure",
            "session_summary",
            "code_symbol",
        }
        if value not in allowed:
            raise ValueError(f"category 必须是 {allowed} 之一")
        return value


class SearchMemoryForm(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class SearchFilesForm(BaseModel):
    query: str = Field(..., min_length=1)
    top_k: int = Field(default=10, ge=1, le=100)


class IndexProjectForm(BaseModel):
    root_dir: str = "."
    force: bool = False


def _entry_to_out(entry: Any) -> MemoryEntryOut:
    return MemoryEntryOut(
        id=entry.id,
        category=entry.category,
        content=entry.content,
        source=entry.source,
        tags=entry.tags,
        importance=entry.importance,
        created_at=entry.created_at,
        updated_at=entry.updated_at,
    )


@router.get("/api/memory/entries")
def list_memory(category: str | None = None) -> dict[str, Any]:
    """列出长期记忆条目"""
    entries = memory_store.list(category=category)
    return {"entries": [_entry_to_out(e) for e in entries]}


@router.post("/api/memory/entries")
def create_memory(form: CreateMemoryForm) -> dict[str, Any]:
    """添加一条长期记忆"""
    try:
        entry = memory_store.add(
            category=form.category,  # type: ignore[arg-type]
            content=form.content,
            source=form.source,
            tags=form.tags,
            importance=form.importance,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"success": True, "entry": _entry_to_out(entry)}


@router.delete("/api/memory/entries/{entry_id}")
def delete_memory(entry_id: str) -> dict[str, Any]:
    """删除指定记忆"""
    if memory_store.delete(entry_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="记忆不存在")


@router.post("/api/memory/search")
def search_memory(form: SearchMemoryForm) -> dict[str, Any]:
    """搜索长期记忆"""
    entries = memory_store.search(form.query, top_k=form.top_k)
    return {"entries": [_entry_to_out(e) for e in entries]}


@router.post("/api/memory/files/search")
def search_project_files(form: SearchFilesForm) -> dict[str, Any]:
    """搜索项目文件索引"""
    entries = memory_store.search_files(form.query, top_k=form.top_k)
    return {
        "files": [
            {
                "path": e.path,
                "symbols": e.symbols,
                "summary": e.summary,
                "snippet": e.snippet,
                "size": e.size,
                "mtime": e.mtime,
            }
            for e in entries
        ]
    }


@router.post("/api/memory/index")
def index_project(form: IndexProjectForm) -> dict[str, Any]:
    """重建项目文件索引"""
    try:
        indexer = ProjectIndexer(memory_store)
        stats = indexer.index_project(root_dir=form.root_dir, force=form.force)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"success": True, "stats": stats}


@router.get("/api/memory/files/status")
def get_file_index_status() -> dict[str, Any]:
    """返回项目文件索引是否存在及其元数据"""
    if not memory_store.file_index_path.exists():
        return {"indexed": False, "updated_at": None, "file_count": 0}
    index = memory_store.get_file_index()
    return {
        "indexed": True,
        "updated_at": index.updated_at,
        "file_count": len(index.files),
        "root": index.root,
        "last_refresh": index.last_refresh,
    }


@router.post("/api/memory/summarize/{session_id}")
def summarize_session(session_id: str) -> dict[str, Any]:
    """总结指定会话并保存到长期记忆"""
    try:
        session = session_store.load(session_id)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    gateway = GatewayClient()
    summarizer = SessionSummarizer(gateway, memory_store)
    ids = summarizer.summarize(session, source=f"session:{session_id}")
    return {"success": True, "added": len(ids), "entry_ids": ids}
