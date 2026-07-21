# MAO v0.1.0-beta.5 Release Notes

This release focuses on one outcome: MAO's model selection and multi-model collaboration should be measurable, explainable, and bounded by offline reproducible contracts before any real-model advantage is claimed.

## Highlights

- **Reproducible engineering benchmark**: a versioned public task contract covers question, diagnosis, small-change, build, review, and migration tasks. Single-model and MAO strategies share isolated workspaces, deterministic response/file/command checks, mutation boundaries, stability signatures, and JSON/Markdown metrics. The default fixture gate runs both synthetic strategies three times in CI without reading keys or calling a Provider, and labels every fixture result as `synthetic_contract` so it cannot be mistaken for real-model evidence.
- **Execution depth contracts**: deterministic `fast`, `standard`, and `deep` budgets constrain main-agent/Worker tool rounds, context usage, Worker concurrency, collaboration review, and mutation verification. User preferences persist through `/depth` and the Web session API, while high-risk safety floors remain non-bypassable and every decision is journaled in RunJournal v4.
- **Explainable model routing**: `ModelRouter` performs at most one bounded upgrade using task type, verified capability states, traceable prices, safe context capacity, health cooldowns, local-model status, and user constraints. Unknown prices never produce savings claims, `/routing fixed` pins the configured main model, runtime failures prefer the user model before the existing failover chain, and RunJournal v5 keeps the full candidate audit while CLI/Web show a concise reason.
- **Controlled multi-model benchmark controls**: `fixed-single`, `auto-route`, and `multi-model` profiles share one harness. A headless `mao benchmark-agent` entry point uses the production Agent stream, an explicit live authorization/spend guard reserves attempts atomically before every network request, and an optional Harbor `BaseInstalledAgent` adapter aligns with the official `0.20.x` contract. The offline gate produces 54 synthetic results across the three profiles without reading keys or calling a Provider.
- **Opt-in adversarial testing**: a default-off, read-only `AdversarialTester` runs only in explicitly enabled `deep change/build` collaboration after all Workers succeed and the deterministic completion audit passes. It receives direct requirements and verification evidence rather than Worker prose, records structured findings in RunJournal, and may downgrade a completed result to blocked but can never upgrade failed deterministic evidence. CLI `/adversarial` and a persistent Web session toggle expose the experiment.
- **Local-model routing contracts**: local/Ollama candidates can be selected at zero estimated cost when capability, health, and context are satisfied, but zero marginal cost cannot bypass health cooldowns, verified capabilities, context capacity, or deep-build reasoning requirements.
- **Catalog single source of truth**: CLI and Web model presets now both derive every entry from `src/models/catalog.py`. A regression test guards against preset drift.

Real Provider comparison remains a separately authorized stage. The `multi-model` live smoke that ran during development exceeded its authorized attempt ceiling and was stopped; all real Provider calls are paused until the owner issues a new cumulative attempt budget. No real-model advantage is claimed in this release.

## Install

Install directly from the published tag:

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.5
mao
# or
mao web
```

Python 3.11 or 3.12 is required. Runtime configuration, keys, sessions and indexes remain local and must not be committed.

## Upgrade Notes

- `mao benchmark-agent` and the Harbor adapter are optional; the `benchmark` extra (`harbor>=0.20,<0.21`) is not installed by default. Harbor `0.20.x` requires Python 3.12, so its real import/Docker smoke is an authorization-time acceptance item on a Python 3.12 host.
- The adversarial testing toggle and `/depth` default to off / `auto`; existing sessions keep their current behavior unless explicitly enabled.
- `/routing fixed` pins the configured main model. Automatic routing performs at most one upgrade and never claims savings when prices are unknown; review any custom routing expectations accordingly.
- Existing `providers.yaml` configurations remain compatible. CLI and Web presets now populate full model metadata from the catalog; regenerated configs may include additional capability/metadata fields that were previously absent for the `ark` Coding Plan preset.

## Verification

- Complete local test collection: `799 passed, 1 warning`; the only warning is an upstream Starlette/httpx deprecation notice. The collection was split across core, real-browser, and replay groups to stay within the local command host's time limit; CI runs the complete suite normally.
- `python scripts/benchmark_engineering.py`: the three fixture strategies each run three times across six task categories, producing 54 stable synthetic results with consistent stability signatures and zero Provider calls.
- Distribution acceptance builds wheel/sdist, checks archive contents, installs dependencies in a clean virtual environment without inherited system packages, and verifies clean CLI plus Web `/health`.
- `pip-audit -r requirements.txt` reports no known vulnerabilities.
- The checksum-verified gitleaks 8.24.3 scan runs in CI and reports no leaks; the local Windows host could not run the gitleaks binary without an external download, so the authoritative secret scan is the CI job.
- Remote CI [run 29829436563](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29829436563) passed on Windows/Ubuntu × Python 3.11/3.12 plus the security job (pip-audit and gitleaks). B5.6 release finalization caught a previously undetected CI failure: the `build/` gitignore rule had hidden the benchmark's build-task fixture, so it was never committed and CI failed while local tests passed; anchoring the rule to `/build/` and tracking the fixture resolved it.
- Python compileall, JavaScript syntax checks and diff hygiene pass locally.
- Real paid Provider calls were not made during unattended acceptance. The earlier private `multi-model` live smoke is not part of the public release and is not used to claim any model advantage.

## Known Limitations

- Automatic routing and the benchmark have offline contracts and mock execution evidence, but no authorized real-model effectiveness data yet; cost or completion-rate advantages cannot be advertised.
- The benchmark validates deterministic contracts; real-model summary quality still needs controlled Provider smoke.
- `mao benchmark-agent` and the Harbor adapter are not container- or OS-sandboxed; tool execution remains constrained by MAO rules only.
- The adversarial tester is an experimental, default-off role; its real-model effect is not yet characterized.
- Local/Ollama routing uses stat metadata and declared capabilities; unverified capabilities never trigger automatic upgrades.
