# MAO v0.1.0-beta.7 Release Notes

This is a security-only patch release. It fixes one P0 found by the v0.2.0 entry-condition audit; there are no feature changes.

## Security Fix

- **`run_command` no longer allows interpreter inline-code execution.** A P0 audit found that `run_command` permitted `python -c`, `node -e`, `node --eval`, `node -p`, and `node --print`: the prefix allowlist allowed these commands and no inline-code check existed (unlike `frontend_smoke` and `benchmark`, which already rejected them). A model could emit `python -c "import os; os.system(...)"` via prompt injection or hallucination to execute arbitrary code that reads `.env` (API key leakage), writes outside the project boundary bypassing `permission_rules`, makes network requests, or destroys data. In `auto` mode this executed without confirmation. `run_command` now rejects these with an `inline_interpreter_code` preflight error. `python -m <module> -c ...` (for example `python -m pytest -c pytest.ini`) is still allowed, because `-c` belongs to the module rather than the interpreter. `readonly` sessions were already unaffected (`run_command` is category `execute`).

## Affected Versions

`v0.1.0-beta.6` and earlier are affected. Upgrade to `v0.1.0-beta.7`.

## Install

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.7
mao --version   # MAO 0.1.0b7
```

## Verification

- Complete local test collection: `856 passed, 1 warning`; the only warning is an upstream Starlette/httpx deprecation notice.
- New tests cover rejection of `python -c` and the `node` inline flags, non-rejection of `python -m pytest -c config`, and script-file invocation; the timeout test no longer relies on `python -c`.
- `pip-audit -r requirements.txt` reports no known vulnerabilities. The checksum-verified gitleaks 8.24.3 scan runs in CI.
- Python compileall, JavaScript syntax checks and diff hygiene pass locally.
- No real Provider calls were made.

## Known Limitations

- Unchanged from `v0.1.0-beta.6`; see its release notes.
- `pytest tests/test_registry.py` in isolation still hits a pre-existing latent circular import (`replay`/`worker_tools`); the full suite and CI are unaffected.
