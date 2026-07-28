"""Application-level safety guards (not an OS sandbox)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from src.tools.safety_guards import (
    has_dangerous_interpreter_invocation,
    is_blocked_fetch_host,
    is_sensitive_path,
    validate_fetch_url,
)
from src.tools.web_tools import fetch_url
from src.tools.worker_tools import edit_file, read_file, run_command, write_file


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.local",
        ".env.production",
        "id_rsa",
        "id_ed25519",
        "secrets.json",
        "credentials.json",
        "cert.pem",
        "app.key",
        Path.home() / ".ssh" / "config",
        Path.home() / ".aws" / "credentials",
    ],
)
def test_is_sensitive_path_matches_common_secret_locations(path):
    assert is_sensitive_path(path) is True


@pytest.mark.parametrize(
    "path",
    [
        "README.md",
        "src/main.py",
        "package.json",
        "tests/test_env_helpers.py",
        "docs/env-setup.md",
    ],
)
def test_is_sensitive_path_allows_normal_project_files(path):
    assert is_sensitive_path(path) is False


def test_read_file_blocks_dotenv(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("SECRET=super-secret\n", encoding="utf-8")

    result = read_file(".env", str(tmp_path))

    assert result.success is False
    assert result.metadata["error_code"] == "sensitive_path"
    assert "敏感路径" in result.error
    assert "super-secret" not in result.error
    assert "super-secret" not in (result.output or "")


def test_write_and_edit_block_sensitive_paths(tmp_path):
    write_result = write_file(".env", "SECRET=1\n", str(tmp_path))
    assert write_result.success is False
    assert write_result.metadata["error_code"] == "sensitive_path"
    assert not (tmp_path / ".env").exists()

    pem = tmp_path / "tls.pem"
    pem.write_text("BEGIN", encoding="utf-8")
    edit_result = edit_file("tls.pem", "BEGIN", "CHANGED", str(tmp_path))
    assert edit_result.success is False
    assert edit_result.metadata["error_code"] == "sensitive_path"
    assert pem.read_text(encoding="utf-8") == "BEGIN"


@pytest.mark.parametrize(
    "command",
    [
        'python -c "print(1)"',
        'python -ic "print(1)"',
        "python -",
        'node -e "1"',
        "node --eval=console.log(1)",
        "node --print=1+1",
        "node -r ./preload.js app.js",
        "node --import ./x.js app.js",
        'py -c "print(1)"',
    ],
)
def test_run_command_rejects_expanded_interpreter_dangers(tmp_path, command):
    result = run_command(command, str(tmp_path))
    assert result.success is False, command
    assert result.metadata["error_code"] == "inline_interpreter_code", command


def test_run_command_still_allows_module_mode_with_c_flag(tmp_path, monkeypatch):
    from unittest.mock import MagicMock

    completed = MagicMock(returncode=0, stdout="ok\n", stderr="")
    monkeypatch.setattr("src.tools.worker_tools.subprocess.run", MagicMock(return_value=completed))
    result = run_command("python -m pytest -c pytest.ini", str(tmp_path))
    assert result.success is True


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["python", "-c", "print(1)"], True),
        (["python", "-m", "pytest", "-c", "pytest.ini"], False),
        (["python", "script.py"], False),
        (["node", "server.js"], False),
        (["node", "--eval=1"], True),
        (["node", "-r", "x.js", "app.js"], True),
    ],
)
def test_has_dangerous_interpreter_invocation_matrix(argv, expected):
    assert has_dangerous_interpreter_invocation(argv) is expected


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8080/admin",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/internal",
        "http://192.168.1.1/",
        "file:///etc/passwd",
        "ftp://example.com/",
    ],
)
def test_validate_fetch_url_blocks_private_and_non_http(url):
    assert validate_fetch_url(url) is not None


def test_validate_fetch_url_allows_public_https():
    with patch(
        "src.tools.safety_guards.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("93.184.216.34", 0))],
    ):
        assert validate_fetch_url("https://example.com/docs") is None


def test_is_blocked_fetch_host_resolves_private_dns():
    with patch(
        "src.tools.safety_guards.socket.getaddrinfo",
        return_value=[(0, 0, 0, "", ("10.1.2.3", 0))],
    ):
        assert is_blocked_fetch_host("evil.example") is True


def test_fetch_url_blocks_localhost_without_network():
    result = fetch_url("http://127.0.0.1:8123/health")
    assert result.success is False
    assert result.metadata["error_code"] == "fetch_url_blocked"
    assert "内网" in result.error or "本地" in result.error
