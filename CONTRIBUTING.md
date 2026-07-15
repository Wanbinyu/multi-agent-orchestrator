# Contributing to MAO

MAO is in beta. Contributions should preserve its core rule: execution claims must be backed by observable evidence, and write access must remain explicit.

## Development setup

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[test]"
python -m pytest -q
```

Use Python 3.11 or 3.12. Before opening a pull request, also run:

```bash
python -m compileall -q src tests scripts run.py
node --check src/ui/static/js/app.js
node --check src/ui/static/js/chat.js
git diff --check
```

## Pull requests

- Keep changes scoped and include tests proportional to the behavioral risk.
- Do not commit `.env`, `config/providers.yaml`, `config/workers.yaml`, sessions, memory, logs, or real model output.
- Mock paid Provider calls in automated tests. Record real smoke tests only after removing prompts, keys and account data.
- Document user-facing configuration or behavior changes in `README.md` and `CHANGELOG.md`.
- Breaking changes require an upgrade note and a minor-version increment while the project is in beta.

Use the issue templates for reproducible defects and Provider compatibility reports. Security issues belong in a private advisory, as described in `SECURITY.md`.
