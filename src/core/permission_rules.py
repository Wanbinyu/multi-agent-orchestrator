"""Deterministic permission rules shared by agents and workers."""
from __future__ import annotations

import fnmatch
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

from src.models.schemas import ApprovalMode


PermissionAction = Literal["allow", "ask", "deny"]
_ACTION_PRIORITY: dict[PermissionAction, int] = {"allow": 1, "ask": 2, "deny": 3}
_PATH_KEYS = ("path", "file", "directory", "root", "cwd")
_COMPLEX_SHELL = re.compile(
    r"\$\(|`|<\(|>\(|>>|<<|(?:^|[^&])&(?!&)|(?<![<>])[<>](?![<>])"
)


@dataclass(frozen=True)
class PermissionRule:
    action: PermissionAction
    tool: str = "*"
    pattern: str = "*"
    justification: str = ""
    match: tuple[str, ...] = ()
    not_match: tuple[str, ...] = ()
    source: str = ""
    index: int = 0

    def summary(self) -> dict[str, object]:
        return {
            "action": self.action,
            "tool": self.tool,
            "pattern": self.pattern,
            "justification": self.justification,
            "match": list(self.match),
            "not_match": list(self.not_match),
            "source": self.source,
            "index": self.index,
        }


@dataclass(frozen=True)
class PermissionDecision:
    action: PermissionAction
    reason: str
    source: str = "session"
    rule: PermissionRule | None = None
    targets: tuple[str, ...] = ()

    def summary(self) -> dict[str, object]:
        return {
            "action": self.action,
            "reason": self.reason,
            "source": self.source,
            "rule": self.rule.summary() if self.rule else None,
            "targets": list(self.targets),
        }


@dataclass
class PermissionRuleSet:
    rules: list[PermissionRule] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def summary(self) -> dict[str, object]:
        return {
            "rule_count": len(self.rules),
            "sources": list(self.sources),
            "diagnostics": list(self.diagnostics),
            "rules": [rule.summary() for rule in self.rules],
        }


class PermissionRuleEngine:
    def __init__(self, rule_set: PermissionRuleSet | None = None, *, workspace: str | Path | None = None):
        self.rule_set = rule_set or PermissionRuleSet()
        self.workspace = Path(workspace or Path.cwd()).expanduser().resolve()

    @classmethod
    def load(
        cls,
        *,
        project_root: str | Path | None = None,
        user_config: str | Path | None = None,
        workspace: str | Path | None = None,
    ) -> "PermissionRuleEngine":
        root = Path(project_root).expanduser().resolve() if project_root else None
        paths: list[Path] = []
        if user_config:
            paths.append(Path(user_config).expanduser())
        if root:
            paths.append(root / ".mao" / "permissions.yaml")
            paths.append(root / ".mao" / "permissions.yml")
        rules = PermissionRuleSet()
        seen: set[str] = set()
        for path in paths:
            key = os.path.normcase(str(path.resolve()))
            if key in seen or not path.is_file():
                continue
            seen.add(key)
            rules.sources.append(str(path.resolve()))
            try:
                data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
                entries = data.get("rules", []) if isinstance(data, dict) else []
                if not isinstance(entries, list):
                    raise ValueError("rules 必须是列表")
                for index, entry in enumerate(entries, start=1):
                    if not isinstance(entry, dict):
                        raise ValueError(f"第 {index} 条规则必须是对象")
                    action = str(entry.get("action", "")).lower()
                    if action not in _ACTION_PRIORITY:
                        raise ValueError(f"第 {index} 条规则 action 必须是 allow/ask/deny")
                    match = _parse_rule_examples(entry.get("match"), field_name="match", index=index)
                    not_match = _parse_rule_examples(
                        entry.get("not_match"), field_name="not_match", index=index
                    )
                    rules.rules.append(
                        PermissionRule(
                            action=action,  # type: ignore[arg-type]
                            tool=str(entry.get("tool", "*")).strip() or "*",
                            pattern=str(entry.get("pattern", "*")).strip() or "*",
                            justification=str(entry.get("justification", "")).strip(),
                            match=match,
                            not_match=not_match,
                            source=str(path.resolve()),
                            index=index,
                        )
                    )
            except (OSError, UnicodeError, yaml.YAMLError, ValueError) as exc:
                rules.diagnostics.append(f"权限规则加载失败 {path}：{exc}")
        engine = cls(rules, workspace=workspace or root or Path.cwd())
        valid_rules: list[PermissionRule] = []
        for rule in rules.rules:
            failure = engine._validate_rule_examples(rule)
            if failure:
                rules.diagnostics.append(
                    f"权限规则自检失败 {rule.source} 第 {rule.index} 条：{failure}；该规则已忽略"
                )
                continue
            valid_rules.append(rule)
        rules.rules = valid_rules
        return engine

    def decide(
        self,
        tool: str,
        params: dict[str, Any] | None,
        *,
        category: str,
        approval_mode: ApprovalMode,
        hard_read_only: bool = False,
    ) -> PermissionDecision:
        params = params or {}
        if category != "read" and (hard_read_only or approval_mode == "readonly"):
            reason = (
                "只读模式：操作被拒绝"
                if approval_mode == "readonly"
                else "只做分析/方案：仅允许只读工具；只读子任务禁止执行非只读工具"
            )
            return PermissionDecision("deny", reason, source="hard-boundary")

        targets, complex_shell = self._targets(tool, params)
        matches: list[tuple[PermissionRule, set[int]]] = []
        for rule in self.rule_set.rules:
            if not fnmatch.fnmatchcase(tool.casefold(), rule.tool.casefold()):
                continue
            matched = {
                index
                for index, target in enumerate(targets)
                if self._matches_pattern(target, rule.pattern, tool=tool)
            }
            if matched:
                matches.append((rule, matched))

        for action in ("deny", "ask"):
            selected = next((rule for rule, _ in reversed(matches) if rule.action == action), None)
            if selected:
                return PermissionDecision(
                    action,  # type: ignore[arg-type]
                    selected.justification or f"命中 {action} 权限规则",
                    source=selected.source,
                    rule=selected,
                    targets=tuple(targets),
                )

        allow_matches = [(rule, covered) for rule, covered in matches if rule.action == "allow"]
        covered = set().union(*(covered for _, covered in allow_matches)) if allow_matches else set()
        if allow_matches and covered == set(range(len(targets))):
            selected = allow_matches[-1][0]
            if complex_shell:
                return PermissionDecision(
                    "ask",
                    "命令包含重定向、替换或后台执行，显式 allow 不能自动批准复杂 shell",
                    source="shell-safety",
                    rule=selected,
                    targets=tuple(targets),
                )
            return PermissionDecision(
                "allow",
                selected.justification or "所有调用片段均命中 allow 权限规则",
                source=selected.source,
                rule=selected,
                targets=tuple(targets),
            )

        if approval_mode == "approve" and category != "read":
            return PermissionDecision("ask", "approve 模式要求确认非只读工具", targets=tuple(targets))
        return PermissionDecision("allow", f"按 {approval_mode} 会话模式执行", targets=tuple(targets))

    def summary(self) -> dict[str, object]:
        return self.rule_set.summary()

    def _targets(self, tool: str, params: dict[str, Any]) -> tuple[list[str], bool]:
        if tool == "run_command":
            command = str(params.get("command", "")).strip()
            segments = _split_command(command) or [command]
            return segments, bool(_COMPLEX_SHELL.search(command))
        for key in _PATH_KEYS:
            value = params.get(key)
            if isinstance(value, str) and value.strip():
                return [self._canonical_path(value)], False
        return [json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)], False

    def _matches_pattern(self, target: str, pattern: str, *, tool: str) -> bool:
        if tool == "run_command":
            return fnmatch.fnmatchcase(target.casefold(), pattern.casefold())
        normalized_pattern = pattern.replace("\\", "/")
        if _looks_like_path_pattern(normalized_pattern):
            if not Path(normalized_pattern).is_absolute() and not re.match(r"^[A-Za-z]:/", normalized_pattern):
                normalized_pattern = str(self.workspace / normalized_pattern).replace("\\", "/")
            normalized_pattern = os.path.normcase(normalized_pattern).replace("\\", "/").casefold()
        patterns = {normalized_pattern.casefold()}
        if "/**/" in normalized_pattern:
            patterns.add(normalized_pattern.replace("/**/", "/").casefold())
        return any(fnmatch.fnmatchcase(target.casefold(), candidate) for candidate in patterns)

    def _canonical_path(self, value: str) -> str:
        path = Path(value).expanduser()
        if not path.is_absolute():
            path = self.workspace / path
        return os.path.normcase(str(path.resolve(strict=False))).replace("\\", "/").casefold()

    def _validate_rule_examples(self, rule: PermissionRule) -> str:
        for example in rule.match:
            if not self._rule_matches_example(rule, example):
                return f"match 示例未命中：{example}"
        for example in rule.not_match:
            if self._rule_matches_example(rule, example):
                return f"not_match 示例错误命中：{example}"
        return ""

    def _rule_matches_example(self, rule: PermissionRule, example: str) -> bool:
        if rule.tool == "run_command":
            targets = _split_command(example) or [example.strip()]
        elif _looks_like_path_pattern(rule.pattern):
            targets = [self._canonical_path(example)]
        else:
            targets = [example]
        return any(
            self._matches_pattern(target, rule.pattern, tool=rule.tool)
            for target in targets
        )


def _looks_like_path_pattern(pattern: str) -> bool:
    return "/" in pattern or "\\" in pattern or pattern.startswith(".") or bool(re.match(r"^[A-Za-z]:", pattern))


def _parse_rule_examples(value: Any, *, field_name: str, index: int) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(f"第 {index} 条规则 {field_name} 必须是字符串列表")
    return tuple(item.strip() for item in value if item.strip())


def _split_command(command: str) -> list[str]:
    """Split common compound-shell operators while respecting simple quotes."""
    parts: list[str] = []
    buffer: list[str] = []
    quote = ""
    index = 0
    while index < len(command):
        char = command[index]
        if quote:
            buffer.append(char)
            if char == quote and (index == 0 or command[index - 1] != "\\"):
                quote = ""
            index += 1
            continue
        if char in ("'", '"'):
            quote = char
            buffer.append(char)
            index += 1
            continue
        operator_length = 0
        if command[index:index + 2] in ("&&", "||"):
            operator_length = 2
        elif char in (";", "|", "\n", "\r"):
            operator_length = 1
        if operator_length:
            value = "".join(buffer).strip()
            if value:
                parts.append(value)
            buffer = []
            index += operator_length
            continue
        buffer.append(char)
        index += 1
    value = "".join(buffer).strip()
    if value:
        parts.append(value)
    return parts
