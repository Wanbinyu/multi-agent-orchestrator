"""P0-4 discovered commands and configurable allowlist."""
from __future__ import annotations

import json

from src.tools.worker_tools import (
    discover_project_commands,
    load_command_allowlist,
    run_command,
)


def test_discover_suggests_runnable_pytest(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_ok.py").write_text(
        "def test_ok():\n    assert True\n", encoding="utf-8"
    )
    result = discover_project_commands(".", str(tmp_path))
    payload = json.loads(result.output)
    assert payload["suggested_run"]["command"] == "python -m pytest -q"
    assert payload["suggested_run"]["cwd"] == str(tmp_path.resolve())
    pytest_cmd = next(item for item in payload["commands"] if item["name"] == "pytest")
    assert pytest_cmd["run"]["command"] == "python -m pytest -q"


def test_discovered_npm_script_can_run_even_without_default_prefix(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"scripts": {"hello": "echo ok"}}),
        encoding="utf-8",
    )
    result = run_command("npm run hello", str(tmp_path), allowed_prefixes=["python "])
    if not result.success:
        assert result.metadata.get("error_code") != "command_not_allowed"


def test_inline_and_pipe_still_denied(tmp_path):
    inline = run_command('python -c "print(1)"', str(tmp_path))
    piped = run_command("python --version | more", str(tmp_path))
    assert inline.metadata["error_code"] == "inline_interpreter_code"
    assert piped.metadata["error_code"] == "shell_syntax"
    assert "bash -c" in piped.error


def test_command_not_allowed_tells_model_to_change_params(tmp_path):
    result = run_command("rm -rf /", str(tmp_path))
    assert result.success is False
    assert result.metadata["error_code"] == "command_not_allowed"
    assert result.metadata["suggested_tool"] == "discover_project_commands"
    assert "bash -c" in result.error


def test_load_command_allowlist_reads_extra_prefixes(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "workers.yaml").write_text(
        "command_allowlist:\n  extra_prefixes:\n    - 'ruff '\n",
        encoding="utf-8",
    )
    prefixes = load_command_allowlist(config)
    assert any(item.startswith("ruff") for item in prefixes)
    assert any(item.startswith("python") for item in prefixes)
