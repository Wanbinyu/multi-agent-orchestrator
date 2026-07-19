"""长期记忆与项目上下文管理

提供：
- MemoryStore：基于 YAML 的记忆条目持久化与关键词检索
- MemoryContextBuilder：根据当前输入查询相关记忆并格式化为上下文
- ProjectIndexer：项目文件索引与代码符号提取
"""
from __future__ import annotations

import re
import hashlib
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field


MemoryCategory = Literal[
    "preference",
    "decision",
    "fact",
    "project_structure",
    "session_summary",
    "code_symbol",
]


class MemoryEntry(BaseModel):
    """一条记忆条目"""

    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    category: MemoryCategory
    content: str = Field(..., min_length=1)
    source: str = "user"
    tags: list[str] = Field(default_factory=list)
    importance: int = Field(default=3, ge=1, le=5)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def model_post_init(self, __context: Any) -> None:
        """确保 content 首尾无多余空白"""
        self.content = self.content.strip()


class MemoryConfig(BaseModel):
    """记忆系统配置"""

    enabled: bool = True
    storage_path: str = "memory"
    max_injected_chars: int = 3000
    indexed_extensions: list[str] = Field(
        default_factory=lambda: [
            ".py", ".yaml", ".yml", ".md", ".js", ".ts", ".json",
            ".jsx", ".tsx", ".html", ".css", ".toml", ".ini", ".cfg",
            ".sh", ".ps1", ".java", ".go", ".rs", ".sql",
        ]
    )
    excluded_dirs: list[str] = Field(
        default_factory=lambda: [
            ".git",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            "__pycache__",
            ".claude",
            "node_modules",
            "venv",
            ".venv",
            "sessions",
            "memory",
            "output",
            "dist",
            "build",
        ]
    )
    max_indexed_file_size: int = 500_000


class FileIndexEntry(BaseModel):
    """单个文件的索引条目"""

    path: str
    mtime: float
    size: int
    content_hash: str = ""
    symbols: list[str] = Field(default_factory=list)
    summary: str = ""
    snippet: str = ""


class FileIndex(BaseModel):
    """项目文件索引"""

    version: int = 2
    root: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    files: dict[str, FileIndexEntry] = Field(default_factory=dict)
    directories: list[str] = Field(default_factory=list)
    tree_paths: list[str] = Field(default_factory=list)
    last_refresh: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# 文本分词与索引工具
# ---------------------------------------------------------------------------


_TOKEN_PATTERN = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]+|[一-鿿]")


def tokenize(text: str) -> list[str]:
    """简单分词：英文按标识符，中文按单字"""
    if not text:
        return []
    return [t.lower() for t in _TOKEN_PATTERN.findall(text)]


def build_inverted_index(items: dict[str, str]) -> dict[str, list[str]]:
    """为每个 item_id 的文本构建倒排索引"""
    index: dict[str, list[str]] = {}
    for item_id, text in items.items():
        tokens = set(tokenize(text))
        for token in tokens:
            index.setdefault(token, []).append(item_id)
    return index


def score_items(query: str, items: dict[str, str], top_k: int = 5) -> list[tuple[str, int]]:
    """按 query 与 item 文本的 token 命中数评分，返回 (item_id, score) 列表"""
    query_tokens = set(tokenize(query))
    if not query_tokens:
        return []

    index = build_inverted_index(items)
    scores: Counter[str] = Counter()

    for token in query_tokens:
        for item_id in index.get(token, []):
            scores[item_id] += 1

    # 归一化：命中 token 数 / query token 总数
    ranked = [(item_id, score / len(query_tokens)) for item_id, score in scores.items()]
    ranked.sort(key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


# ---------------------------------------------------------------------------
# MemoryStore
# ---------------------------------------------------------------------------


class MemoryStore:
    """记忆持久化存储"""

    def __init__(self, config_path: str = "config/memory.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        # storage_path 相对路径以配置文件所在目录为基准解析，避免运行时 chdir 影响
        base_dir = self.config_path.parent.resolve()
        self.storage_dir = (base_dir / self.config.storage_path).resolve()
        self.entries_path = self.storage_dir / "entries.yaml"
        self.file_index_path = self.storage_dir / "file_index.yaml"
        self.storage_dir.mkdir(parents=True, exist_ok=True)

        self._entries: dict[str, MemoryEntry] = {}
        self._file_index: FileIndex = FileIndex()
        self._file_index_load_failed = False
        self._load_entries()
        self._load_file_index()

    def _load_config(self) -> MemoryConfig:
        if not self.config_path.exists():
            return MemoryConfig()
        with open(self.config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return MemoryConfig(**data)

    def _load_entries(self) -> None:
        if not self.entries_path.exists():
            return
        with open(self.entries_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or []
        for item in data:
            try:
                entry = MemoryEntry(**item)
                self._entries[entry.id] = entry
            except Exception:
                continue

    def _save_entries(self) -> None:
        data = [entry.model_dump() for entry in self._entries.values()]
        with open(self.entries_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    def _load_file_index(self) -> None:
        if not self.file_index_path.exists():
            return
        try:
            with open(self.file_index_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            self._file_index = FileIndex(**data)
        except Exception:
            self._file_index = FileIndex()
            self._file_index_load_failed = True

    def _save_file_index(self) -> None:
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        temp_path = self.file_index_path.with_suffix(".yaml.tmp")
        with open(temp_path, "w", encoding="utf-8", newline="\n") as f:
            yaml.dump(
                self._file_index.model_dump(),
                f,
                allow_unicode=True,
                sort_keys=False,
                default_flow_style=False,
            )
        temp_path.replace(self.file_index_path)
        self._file_index_load_failed = False

    # --- entries API ---

    def add(
        self,
        content: str,
        category: MemoryCategory,
        source: str = "user",
        tags: list[str] | None = None,
        importance: int = 3,
    ) -> MemoryEntry:
        """添加一条记忆"""
        entry = MemoryEntry(
            category=category,
            content=content,
            source=source,
            tags=tags or [],
            importance=importance,
        )
        self._entries[entry.id] = entry
        self._save_entries()
        return entry

    def get(self, entry_id: str) -> MemoryEntry | None:
        return self._entries.get(entry_id)

    def delete(self, entry_id: str) -> bool:
        if entry_id not in self._entries:
            return False
        del self._entries[entry_id]
        self._save_entries()
        return True

    def list(self, category: str | None = None, tag: str | None = None) -> list[MemoryEntry]:
        results = list(self._entries.values())
        if category:
            results = [e for e in results if e.category == category]
        if tag:
            results = [e for e in results if tag in e.tags]
        return sorted(results, key=lambda e: e.created_at, reverse=True)

    def search(self, query: str, top_k: int = 5) -> list[MemoryEntry]:
        """关键词搜索记忆条目"""
        if not query.strip() or not self._entries:
            return []
        items = {e.id: f"{e.category} {e.content} {' '.join(e.tags)}" for e in self._entries.values()}
        ranked = score_items(query, items, top_k=top_k)
        return [self._entries[item_id] for item_id, _ in ranked if item_id in self._entries]

    # --- file index API ---

    def get_file_index(self) -> FileIndex:
        return self._file_index

    @property
    def file_index_load_failed(self) -> bool:
        return self._file_index_load_failed

    def search_files(self, query: str, top_k: int = 5) -> list[FileIndexEntry]:
        """关键词搜索项目文件索引"""
        if not query.strip() or not self._file_index.files:
            return []
        items = {
            path: f"{entry.path} {' '.join(entry.symbols)} {entry.summary} {entry.snippet}"
            for path, entry in self._file_index.files.items()
        }
        ranked = score_items(query, items, top_k=top_k)
        return [self._file_index.files[path] for path, _ in ranked if path in self._file_index.files]

    def update_file_index(self, index: FileIndex) -> None:
        self._file_index = index
        self._save_file_index()


# ---------------------------------------------------------------------------
# MemoryContextBuilder
# ---------------------------------------------------------------------------


class MemoryContextBuilder:
    """根据用户输入构建相关记忆上下文"""

    def __init__(self, store: MemoryStore):
        self.store = store

    def build_context(self, query: str, max_chars: int | None = None) -> str:
        """返回格式化记忆上下文字符串"""
        if not self.store.config.enabled:
            return ""

        max_chars = max_chars or self.store.config.max_injected_chars
        entries = self.store.search(query, top_k=20)
        if not entries:
            return ""

        lines: list[str] = ["【项目记忆与上下文】", "以下记忆可能与当前对话相关，请在回复时参考："]
        current_len = sum(len(line) + 1 for line in lines)

        for entry in entries:
            # 按重要性加权排序后，重要记忆优先
            line = f"[{entry.category}] {entry.content}"
            if current_len + len(line) + 1 > max_chars:
                break
            lines.append(line)
            current_len += len(line) + 1

        lines.append("【项目记忆结束】")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# ProjectIndexer
# ---------------------------------------------------------------------------


_PYTHON_SYMBOL_RE = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)|^\s*class\s+(\w+)", re.MULTILINE)
_JS_SYMBOL_RE = re.compile(
    r"(?:^|\s)(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)"
    r"|^\s*class\s+(\w+)"
    r"|^\s*const\s+(\w+)\s*="
    r"|^\s*let\s+(\w+)\s*="
    r"|^\s*var\s+(\w+)\s*=",
    re.MULTILINE,
)


def _extract_symbols(content: str, ext: str) -> list[str]:
    """从代码内容中提取符号名"""
    if ext == ".py":
        matches = _PYTHON_SYMBOL_RE.findall(content)
    elif ext in (".js", ".ts", ".jsx", ".tsx"):
        matches = _JS_SYMBOL_RE.findall(content)
    else:
        return []

    symbols: list[str] = []
    for groups in matches:
        for g in groups:
            if g:
                symbols.append(g)
    return symbols


def _summarize_file(content: str, ext: str) -> str:
    """生成文件一句话摘要"""
    lines = content.strip().splitlines()
    if not lines:
        return ""
    first = lines[0].strip()
    if first.startswith(("#", "//", "\"\"\"", "'''", "/*")):
        return first.lstrip("# /*\"'").strip()[:200]
    if ext == ".py" and len(lines) > 1:
        second = lines[1].strip()
        if second.startswith(("\"\"\"", "'''")):
            return second.lstrip("\"'").strip()[:200]
    return ""


class ProjectIndexer:
    """项目文件索引器"""

    def __init__(self, store: MemoryStore):
        self.store = store
        self.config = store.config

    def index_project(self, root_dir: str | Path = ".", force: bool = False) -> dict[str, Any]:
        """Refresh the project index while reading only changed text files."""
        root = Path(root_dir).resolve()
        if not root.exists() or not root.is_dir():
            raise FileNotFoundError(f"项目目录不存在：{root_dir}")
        excluded = {item.casefold() for item in self.config.excluded_dirs}
        extensions = set(self.config.indexed_extensions)
        max_size = self.config.max_indexed_file_size
        storage_dir = self.store.storage_dir.resolve()
        config_path = self.store.config_path.resolve()

        previous_index = self.store.get_file_index()
        root_changed = bool(
            previous_index.files and previous_index.root != str(root)
        )
        cache_recovered = self.store.file_index_load_failed
        existing = (
            previous_index.files
            if not force and not root_changed and not cache_recovered
            else {}
        )
        new_files: dict[str, FileIndexEntry] = {}
        directories: list[str] = []
        tree_paths: list[str] = []
        scanned = 0
        added = 0
        updated = 0
        reused = 0
        read = 0
        metadata_only = 0
        errors = 0

        for path in root.rglob("*"):
            if path.is_symlink():
                continue
            try:
                relative = path.relative_to(root)
            except ValueError:
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            if any(part.casefold() in excluded for part in relative.parts):
                continue
            resolved = path.resolve()
            if resolved == config_path:
                continue
            try:
                resolved.relative_to(storage_dir)
                continue
            except ValueError:
                pass
            rel_path = str(relative).replace("\\", "/")
            if path.is_dir():
                directories.append(rel_path)
                continue
            if not path.is_file():
                continue
            tree_paths.append(rel_path)
            if path.suffix.lower() not in extensions:
                continue
            try:
                stat = path.stat()
            except OSError:
                errors += 1
                continue
            if stat.st_size > max_size:
                continue
            mtime = stat.st_mtime
            scanned += 1

            previous = existing.get(rel_path)
            if (
                previous is not None
                and previous.mtime == mtime
                and previous.size == stat.st_size
                and previous.content_hash
            ):
                new_files[rel_path] = previous
                reused += 1
                continue
            try:
                raw = path.read_bytes()
                read += 1
            except OSError:
                errors += 1
                if previous is not None:
                    new_files[rel_path] = previous
                continue
            content_hash = hashlib.sha256(raw).hexdigest()
            if previous is not None and previous.content_hash == content_hash:
                new_files[rel_path] = previous.model_copy(update={
                    "mtime": mtime,
                    "size": stat.st_size,
                })
                metadata_only += 1
                continue
            content = raw.decode("utf-8", errors="ignore")
            if previous is not None:
                updated += 1
            else:
                added += 1

            suffix = path.suffix.lower()
            symbols = _extract_symbols(content, suffix)
            summary = _summarize_file(content, suffix)
            snippet = content[:500].strip()

            new_files[rel_path] = FileIndexEntry(
                path=rel_path,
                mtime=mtime,
                size=stat.st_size,
                content_hash=content_hash,
                symbols=symbols,
                summary=summary,
                snippet=snippet,
            )
        removed = len(set(existing) - set(new_files))
        stats: dict[str, Any] = {
            "scanned": scanned,
            "read": read,
            "reused": reused,
            "added": added,
            "updated": updated,
            "metadata_only": metadata_only,
            "removed": removed,
            "errors": errors,
            "total": len(new_files),
            "directories": len(directories),
            "tree_entries": len(directories) + len(tree_paths),
            "root_changed": root_changed,
            "cache_recovered": cache_recovered,
            "force": force,
        }
        index = FileIndex(
            root=str(root),
            files=new_files,
            directories=sorted(dict.fromkeys(directories)),
            tree_paths=sorted(dict.fromkeys(tree_paths)),
            last_refresh=stats,
        )
        self.store.update_file_index(index)
        return stats


def render_indexed_project_tree(
    index: FileIndex,
    *,
    max_depth: int = 4,
    max_entries: int = 300,
) -> tuple[str, int, int, bool]:
    """Render a stable tree from cached relative paths without filesystem reads."""
    paths = [(path, True) for path in index.directories]
    paths.extend((path, False) for path in index.tree_paths)
    children: dict[str, list[tuple[str, bool]]] = {}
    for path, is_dir in paths:
        parts = Path(path).parts
        if not parts:
            continue
        parent = "/".join(parts[:-1])
        item = (parts[-1], is_dir)
        if item not in children.setdefault(parent, []):
            children[parent].append(item)
    for items in children.values():
        items.sort(key=lambda item: (not item[1], item[0].casefold(), item[0]))

    lines: list[str] = []
    count = 0
    depth_truncated = 0
    entries_truncated = False

    def walk(parent: str, prefix: str, depth: int) -> None:
        nonlocal count, depth_truncated, entries_truncated
        items = children.get(parent, [])
        for position, (name, is_dir) in enumerate(items):
            if count >= max_entries:
                entries_truncated = True
                return
            is_last = position == len(items) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{name}{'/' if is_dir else ''}")
            count += 1
            if not is_dir:
                continue
            child = f"{parent}/{name}".strip("/")
            if depth >= max_depth:
                if children.get(child):
                    depth_truncated += 1
                continue
            walk(child, prefix + ("    " if is_last else "│   "), depth + 1)
            if entries_truncated:
                return

    if max_depth == 0:
        depth_truncated = 1 if paths else 0
    else:
        walk("", "", 1)
    return "\n".join(lines), count, depth_truncated, entries_truncated
