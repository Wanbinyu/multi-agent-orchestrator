"""Application logging setup and secret redaction."""
from __future__ import annotations

import logging
from pathlib import Path

from src.core.logging_setup import (
    get_logger,
    redact_secrets,
    reset_logging_for_tests,
    setup_logging,
)


def setup_function() -> None:
    reset_logging_for_tests()


def teardown_function() -> None:
    reset_logging_for_tests()


def test_redact_secrets_masks_keys_and_bearer():
    raw = "Authorization: Bearer abcdefghijklmnop sk-1234567890abcdef ark-abcdef123456"
    out = redact_secrets(raw)
    assert "abcdefghijklmnop" not in out
    assert "sk-1234567890abcdef" not in out
    assert "ark-abcdef123456" not in out
    assert "sk-***" in out
    assert "ark-***" in out
    # authorization header value is fully redacted
    assert "Authorization:" in out
    assert "***" in out


def test_setup_logging_writes_redacted_file(tmp_path: Path):
    log_path = tmp_path / "mao.log"
    setup_logging(level="INFO", log_file=log_path, force=True)
    logger = get_logger("test")
    logger.info("using key sk-SUPERSECRETOKEN123456")
    # Flush handlers
    for handler in logging.getLogger("mao").handlers:
        handler.flush()
    text = log_path.read_text(encoding="utf-8")
    assert "sk-***" in text
    assert "SUPERSECRETOKEN" not in text


def test_json_format_emits_one_object_per_line(tmp_path: Path, capsys):
    setup_logging(level="INFO", fmt="json", force=True)
    get_logger("json_test").warning("hello world")
    # stream handler goes to stderr
    err = capsys.readouterr().err
    assert '"level": "WARNING"' in err or '"level":"WARNING"' in err.replace(" ", "")
    assert "hello world" in err
