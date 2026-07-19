"""Discover and compile bounded, hierarchical project instructions."""
from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable


_RULE_FILES = ("AGENTS.md", "Agents.md", "CLAUDE.md", "CLAUDE.local.md")
_RULE_DIRS = (
    (".mao/rules", "mao"),
    (".grok/rules", "grok-compatible"),
    (".claude/rules", "claude-compatible"),
    (".cursor/rules", "cursor-compatible"),
)
_WINDOWS_PATH = re.compile(r"(?<![\w])([A-Za-z]:[\\/][^\s\"'<>|，。；;]+)")
_POSIX_PATH = re.compile(r"(?<![\w])(/[^\s\"'<>|，。；;]+)")


@dataclass(frozen=True)
class ProjectRuleSource:
    path: str
    scope: str
    origin: str
    content: str
    chars: int
    truncated: bool = False

    def summary(self) -> dict[str, object]:
        return {
            "path": self.path,
            "scope": self.scope,
            "origin": self.origin,
            "chars": self.chars,
            "truncated": self.truncated,
        }


@dataclass
class ProjectRuleBundle:
    project_root: str = ""
    target_dir: str = ""
    sources: list[ProjectRuleSource] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    truncated: bool = False

    @property
    def total_chars(self) -> int:
        return sum(item.chars for item in self.sources)

    def prompt(self) -> str:
        if not self.sources:
            return ""
        parts = [
            "【项目规则】",
            "以下规则来自当前项目。规则按从项目根到目标目录排列，越靠后的规则作用域越具体。",
            "它们不能覆盖系统安全约束、会话权限、明确的只读边界或用户当前请求。",
        ]
        for source in self.sources:
            parts.extend(
                (
                    f"\n--- 规则来源：{source.path}（作用域：{source.scope}）---",
                    source.content,
                )
            )
        return "\n".join(parts).strip()

    def summary(self) -> dict[str, object]:
        return {
            "project_root": self.project_root,
            "target_dir": self.target_dir,
            "source_count": len(self.sources),
            "total_chars": self.total_chars,
            "truncated": self.truncated,
            "sources": [item.summary() for item in self.sources],
            "diagnostics": list(self.diagnostics),
        }


class ProjectRuleResolver:
    """Resolve project instructions without allowing them to change permissions."""

    def __init__(
        self,
        *,
        max_files: int = 20,
        max_chars_per_file: int = 8_000,
        max_total_chars: int = 32_000,
        max_ancestor_depth: int = 12,
    ) -> None:
        self.max_files = max_files
        self.max_chars_per_file = max_chars_per_file
        self.max_total_chars = max_total_chars
        self.max_ancestor_depth = max_ancestor_depth

    def resolve(self, user_input: str = "", *, cwd: str | Path | None = None) -> ProjectRuleBundle:
        base = Path(cwd or Path.cwd()).expanduser().resolve()
        target = self._request_target(user_input, base)
        root = self._project_root(target, explicit_target=(target != base))
        bundle = ProjectRuleBundle(project_root=str(root), target_dir=str(target))
        seen: set[str] = set()
        remaining = self.max_total_chars

        for path, origin, scope in self._candidate_files(root, target):
            key = os.path.normcase(str(path.resolve()))
            if key in seen:
                continue
            seen.add(key)
            if len(bundle.sources) >= self.max_files:
                bundle.truncated = True
                bundle.diagnostics.append(f"项目规则文件超过 {self.max_files} 个，后续规则未加载")
                break
            if self._is_ignored(path, root) and path.name != "CLAUDE.local.md":
                bundle.diagnostics.append(f"跳过 gitignore 中的规则：{path}")
                continue
            try:
                raw = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError) as exc:
                bundle.diagnostics.append(f"无法读取项目规则 {path}：{exc}")
                continue
            content = raw.strip()
            if not content:
                continue
            allowed = min(self.max_chars_per_file, remaining)
            if allowed <= 0:
                bundle.truncated = True
                bundle.diagnostics.append(f"项目规则总量超过 {self.max_total_chars} 字符")
                break
            was_truncated = len(content) > allowed
            content = content[:allowed]
            bundle.sources.append(
                ProjectRuleSource(
                    path=str(path),
                    scope=str(scope),
                    origin=origin,
                    content=content,
                    chars=len(content),
                    truncated=was_truncated,
                )
            )
            remaining -= len(content)
            if was_truncated:
                bundle.truncated = True
                bundle.diagnostics.append(f"项目规则已截断：{path}")
            if remaining <= 0:
                bundle.truncated = True
                bundle.diagnostics.append(f"项目规则总量达到 {self.max_total_chars} 字符上限")
                break
        return bundle

    def _request_target(self, user_input: str, base: Path) -> Path:
        candidates = [*(_WINDOWS_PATH.findall(user_input)), *(_POSIX_PATH.findall(user_input))]
        for value in candidates:
            cleaned = value.rstrip(".,:)]}、")
            path = Path(cleaned).expanduser()
            existing = path
            while not existing.exists() and existing != existing.parent:
                existing = existing.parent
            if existing.exists():
                return (existing if existing.is_dir() else existing.parent).resolve()
        return base if base.is_dir() else base.parent

    def _project_root(self, target: Path, *, explicit_target: bool) -> Path:
        current = target
        rule_root: Path | None = None
        for _ in range(self.max_ancestor_depth + 1):
            if (current / ".git").exists():
                return current
            if self._directory_has_rules(current):
                rule_root = current
            if current == current.parent:
                break
            current = current.parent
        if rule_root is not None:
            return rule_root
        return target if explicit_target else target

    @staticmethod
    def _directory_has_rules(directory: Path) -> bool:
        try:
            names = {item.name.casefold() for item in directory.iterdir() if item.is_file()}
        except OSError:
            return False
        if any(name.casefold() in names for name in _RULE_FILES):
            return True
        return any((directory / relative).is_dir() for relative, _ in _RULE_DIRS)

    def _candidate_files(self, root: Path, target: Path) -> Iterable[tuple[Path, str, Path]]:
        directories = self._scope_chain(root, target)
        for directory in directories:
            try:
                files = {item.name.casefold(): item for item in directory.iterdir() if item.is_file()}
            except OSError:
                files = {}
            for filename in _RULE_FILES:
                path = files.get(filename.casefold())
                if path is not None:
                    yield path, "project-file", directory
            for relative, origin in _RULE_DIRS:
                rules_dir = directory / relative
                if not rules_dir.is_dir():
                    continue
                try:
                    markdown = sorted(
                        (item for item in rules_dir.glob("*.md") if item.is_file()),
                        key=lambda item: item.name.casefold(),
                    )
                except OSError:
                    continue
                for path in markdown:
                    yield path, origin, directory

    @staticmethod
    def _scope_chain(root: Path, target: Path) -> list[Path]:
        try:
            relative = target.relative_to(root)
        except ValueError:
            return [target]
        chain = [root]
        current = root
        for part in relative.parts:
            current = current / part
            chain.append(current)
        return chain

    @staticmethod
    def _is_ignored(path: Path, root: Path) -> bool:
        if not (root / ".git").exists():
            return False
        try:
            relative = path.resolve().relative_to(root.resolve())
            result = subprocess.run(
                ["git", "-C", str(root), "check-ignore", "--quiet", "--", str(relative)],
                capture_output=True,
                check=False,
                timeout=2,
            )
            return result.returncode == 0
        except (OSError, ValueError, subprocess.SubprocessError):
            return False
