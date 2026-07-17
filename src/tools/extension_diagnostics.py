"""Bounded, user-safe diagnostics for optional extensions."""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, TypedDict


MAX_EXTENSION_DIAGNOSTICS = 10
MAX_DIAGNOSTIC_TEXT = 160


class ExtensionDiagnostic(TypedDict, total=False):
    source: str
    code: str
    message: str
    action: str
    config_path: str
    entry: str
    error_type: str


class ExtensionLoadResult(TypedDict):
    hooks: int
    mcp_sources: int
    diagnostics: list[ExtensionDiagnostic]


def make_extension_diagnostic(
    *,
    source: str,
    code: str,
    message: str,
    action: str,
    config_path: str | Path | None = None,
    entry: str | None = None,
    error: Exception | None = None,
) -> ExtensionDiagnostic:
    """Create a diagnostic without retaining exception text or config values."""
    diagnostic: ExtensionDiagnostic = {
        "source": _bounded(source),
        "code": _bounded(code),
        "message": _bounded(message),
        "action": _bounded(action),
    }
    if config_path is not None:
        # A basename identifies the config without exposing a user's home path.
        diagnostic["config_path"] = _bounded(Path(config_path).name)
    if entry is not None:
        diagnostic["entry"] = _bounded(entry)
    if error is not None:
        diagnostic["error_type"] = _bounded(type(error).__name__)
    return diagnostic


def bounded_diagnostics(
    diagnostics: Iterable[ExtensionDiagnostic],
) -> list[ExtensionDiagnostic]:
    """Return defensive copies capped to the public diagnostic limit."""
    return [dict(item) for item in list(diagnostics)[:MAX_EXTENSION_DIAGNOSTICS]]


def empty_extension_result() -> ExtensionLoadResult:
    return {"hooks": 0, "mcp_sources": 0, "diagnostics": []}


def copy_extension_result(result: ExtensionLoadResult) -> ExtensionLoadResult:
    return {
        "hooks": result["hooks"],
        "mcp_sources": result["mcp_sources"],
        "diagnostics": bounded_diagnostics(result["diagnostics"]),
    }


def _bounded(value: str) -> str:
    return str(value).replace("\r", " ").replace("\n", " ")[:MAX_DIAGNOSTIC_TEXT]
