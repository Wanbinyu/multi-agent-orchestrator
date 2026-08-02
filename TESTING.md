# Testing Guide

## Requirements

- Python 3.11+
- Project dependencies: `pip install -r requirements.txt`

## Running tests

```bash
# Run all tests
python -m pytest

# Run a single file
python -m pytest tests/test_orchestrator.py

# Verbose output
python -m pytest -v

# Show print output
python -m pytest -s

# Coverage report (requires pytest-cov)
pip install pytest-cov
python -m pytest --cov=src --cov-report=term-missing
```

## Test design principles

- **No real HTTP requests**: the Provider layer is mocked with `unittest.mock.MagicMock`.
- **Retry tests do not wait**: mock `src.gateway.client.time.sleep` to speed them up.
- **Filesystem tests are isolated**: use pytest’s built-in `tmp_path` fixture.
- **CLI tests use CliRunner**: call `typer.testing.CliRunner` to verify command behavior.
- **Chinese assertions**: error messages keep the original Chinese text so they match the implementation.

## Test layout

| File | Coverage |
|---|---|
| `tests/test_orchestrator.py` | Orchestrator task splitting, JSON parsing, model fallback |
| `tests/test_gateway_client.py` | GatewayClient config load, retries, billing, main model |
| `tests/test_worker_e2e.py` | Worker execution, file writes, tool calls, exception handling |
| `tests/test_run_cli.py` | CLI commands, help, default subcommand injection |
| `tests/test_file_tools.py` | Code-block parsing, filename inference, file write/append |
| `tests/test_dispatcher.py` | DAG parallelism, dependency order, cascade failure |
| `tests/test_dispatcher_edge_cases.py` | Empty tasks, cyclic dependencies, missing dependencies |
| `tests/test_model_router.py` | Model routing resolution |
| `tests/test_provider_model_map.py` | Provider model_map mapping |
| `tests/test_provider_rotation.py` | API key rotation, map_model_id fallback |
| `tests/test_reviewer.py` | Reviewer JSON parsing |
| `tests/test_setup_wizard.py` | Setup wizard helper functions |
| `tests/test_worker.py` | Worker tool instructions and tool_calls handling |
| `tests/test_worker_tools.py` | Direct tests for read_file / run_command |
| `tests/test_connection_test.py` | Provider connectivity tests |
| `tests/test_model_catalog.py` | Built-in model catalog |

## Adding new tests

1. Prefer in-module helper functions to build inputs; avoid depending on global fixtures.
2. Where a gateway is needed, use `MagicMock(spec=GatewayClient)`.
3. Where config files are needed, write them under `tmp_path`.
4. When asserting error messages, keep the original Chinese text.

## Local verification

```bash
cd E:\multi-agent-orchestrator

# Full suite
python -m pytest -q

# Verify CLI help
python run.py --help
python run.py run --help
python run.py setup --help
python run.py agent-setup --help
```

Expected results:

- All tests pass
- No real API calls
- CLI help displays normally
