"""MAO structured application logging with secret redaction.

Environment:
  MAO_LOG_LEVEL   DEBUG|INFO|WARNING|ERROR|CRITICAL  (default INFO)
  MAO_LOG_FILE    optional path; when set, also write UTF-8 logs to file
  MAO_LOG_FORMAT  ``text`` (default) or ``json``

Logging is process-wide and idempotent. Values that look like API keys are
redacted before emit. This is **not** a substitute for RunJournal evidence.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_CONFIGURED = False
_LOGGER_NAME = "mao"

# Shared redaction patterns (aligned with sanitize_feedback_text, kept local to
# avoid import cycles from tools/scripts).
_REDACT_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._\-+/=]{8,}"), "Bearer ***"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{10,}"), "sk-***"),
    (re.compile(r"\bark-[A-Za-z0-9_\-]{10,}"), "ark-***"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "ghp_***"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github_pat_***"),
    (
        re.compile(
            r"(?i)\b(api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*\S+"
        ),
        r"\1=***",
    ),
    (re.compile(r"(?i)(authorization\s*:\s*)\S+"), r"\1***"),
    (
        re.compile(r"([?&](?:token|key|api_key|access_token)=)[^&\s]+", re.I),
        r"\1***",
    ),
]


def redact_secrets(text: str) -> str:
    """Return *text* with common credential patterns replaced."""
    out = text
    for pattern, repl in _REDACT_PATTERNS:
        out = pattern.sub(repl, out)
    return out


class RedactingFilter(logging.Filter):
    """Filter that redacts secrets in the formatted message and args."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact_secrets(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {
                        key: redact_secrets(str(value))
                        if isinstance(value, str)
                        else value
                        for key, value in record.args.items()
                    }
                elif isinstance(record.args, tuple):
                    record.args = tuple(
                        redact_secrets(arg) if isinstance(arg, str) else arg
                        for arg in record.args
                    )
        except Exception:  # noqa: BLE001 - logging must never break callers
            pass
        return True


class JsonFormatter(logging.Formatter):
    """One JSON object per line for machine consumption."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        for key in ("run_id", "session_id", "task_id", "model", "provider", "error_code"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def _parse_level(value: str | None) -> int:
    name = (value or "INFO").strip().upper()
    return getattr(logging, name, logging.INFO)


def setup_logging(
    *,
    level: str | None = None,
    log_file: str | Path | None = None,
    fmt: str | None = None,
    force: bool = False,
) -> logging.Logger:
    """Configure the root ``mao`` logger once (or again when *force*)."""
    global _CONFIGURED
    if _CONFIGURED and not force:
        return logging.getLogger(_LOGGER_NAME)

    level_value = _parse_level(level or os.environ.get("MAO_LOG_LEVEL", "INFO"))
    format_name = (fmt or os.environ.get("MAO_LOG_FORMAT", "text")).strip().lower()
    file_path = log_file or os.environ.get("MAO_LOG_FILE") or ""

    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    logger.setLevel(level_value)
    logger.propagate = False

    redactor = RedactingFilter()
    if format_name == "json":
        formatter: logging.Formatter = JsonFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s %(levelname)s [mao] %(name)s: %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )

    stream_handler = logging.StreamHandler(sys.stderr)
    stream_handler.setLevel(level_value)
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(redactor)
    logger.addHandler(stream_handler)

    if file_path:
        path = Path(file_path).expanduser()
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setLevel(level_value)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        logger.addHandler(file_handler)

    _CONFIGURED = True
    logger.debug(
        "logging configured level=%s format=%s file=%s",
        logging.getLevelName(level_value),
        format_name,
        file_path or "-",
    )
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    """Return a child of the MAO logger; configures defaults if needed."""
    if not _CONFIGURED:
        setup_logging()
    if not name or name == _LOGGER_NAME:
        return logging.getLogger(_LOGGER_NAME)
    if name.startswith(f"{_LOGGER_NAME}."):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")


def reset_logging_for_tests() -> None:
    """Test helper: drop handlers so the next setup_logging reconfigures."""
    global _CONFIGURED
    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    _CONFIGURED = False
