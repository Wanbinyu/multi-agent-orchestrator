# MAO Migration and Upgrade Guide

This guide summarizes changes users should note between `v0.1.0-beta.3` and `v0.1.0-beta.6`, plus key points for migrating toward `v0.2.0`. Full per-version changes are in the corresponding `docs/RELEASE_NOTES_v0.1.0-beta.*.md`.

MAO may include breaking changes during `0.x`; they are called out explicitly in Release Notes and this guide. Before upgrading, back up local `config/`, `sessions/`, and `memory/` (these are not committed to the repo).

## Upgrade

```bash
pipx upgrade multi-agent-orchestrator
# or from source
git pull --ff-only
python -m pip install -e ".[test]"
python -m pytest -q
```

After upgrade, the first `mao` run migrates local config as needed; older `providers.yaml`/`workers.yaml` remain compatible.

## beta.3 -> beta.4

- **Dual permission-mode gate**: `auto` may write/execute directly; `approve` only confirms non-read-only tools; `readonly` may read but rejects writes/commands. Unclassified requests follow the session mode and are no longer misreported as engineering changes. Phrases like "help me do / set up …" are recognized as build.
- **Session resume**: when the latest run is `running`/`blocked` or has an incomplete plan, CLI `/resume` and the Web banner block new messages until the user explicitly continues or abandons. Continue only hands unfinished-step checkpoints to a new run; it does not automatically replay completed work.
- **Layered compaction**: L0 artifact references + L1 structured summaries + L2 recent full text; native `tool_use`/`tool_result` pairs are not split apart.
- **Reviewer defaults to restricted**: reads requirements/plan/files/direct evidence only, not Worker body text; switch to `full` via `workers.yaml`.
- **Persistent Plan mode**: CLI/Web can enter, revise, approve, and cancel plans.

## beta.4 -> beta.5

- **Execution depth**: `/depth auto|fast|standard|deep`; high-risk tasks cannot bypass deterministic verification with `fast`.
- **Explainable routing**: `/routing fixed` locks the primary model; auto routing upgrades at most once; unverified capabilities do not upgrade; unknown pricing does not claim savings.
- **Model catalog as single source of truth**: CLI and Web presets are unified from `src/models/catalog.py`; `ark` Coding Plan presets now take values from the catalog (regenerated configs may gain capability/metadata fields).
- **Adversarial testing**: off by default; `/adversarial on|off` runs a read-only `AdversarialTester` only in explicitly enabled `deep change/build` collaboration.
- **Benchmarks**: `python scripts/benchmark_engineering.py` runs offline; results are `synthetic_contract` and do not represent real model performance.

## beta.5 -> beta.6

- **Plugin API v0**: plugins are disabled by default; enable explicitly in `config/plugins.yaml` (added to `.gitignore`).
- **`contrib/example_tools.py` pattern**: the old import-to-register pattern still works, but distributed plugins should use the Plugin API (manifest + entry point + enable gate). See [`plugin-development-guide.md`](plugin-development-guide.md).
- **`mao plugin` CLI**: new `list/doctor/enable/disable` subcommands.
- **Web**: new `GET /api/plugins` and a read-only chat "Plugins" tab.
- **Isolation**: `ToolRegistry`/`HookRegistry` gain unregister methods so plugin load failures can roll back.

## Migrating Toward v0.2.0

`v0.2.0` is not released automatically. Historical version gates: [`archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md`](archive/completed-beta/version-plan-v0.1.0-beta.3-to-beta.6.md) §6; current execution follows [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md). Migration highlights:

- **Provider compatibility matrix**: after upgrade, check capability status for Providers you use (`unverified`/`supported`); unverified capabilities do not participate in auto-routing upgrades.
- **Plugin API compatibility**: during `0.x` the Plugin API may still evolve with breaks; plugin authors should pin `mao_api_version` and watch Release Notes. Compatibility rules: [`Plugin-API-compatibility-policy.md`](Plugin-API-compatibility-policy.md).
- **Real benchmarks**: B5.4 real multi-model comparison is paused until the owner re-authorizes cumulative attempt bounds; until then, MAO benchmark data must not be used to claim real model superiority.
- **Config locations unchanged**: `config/`, `sessions/`, `memory/`, and `.env` remain local and are not committed.

## Rollback

If issues appear after upgrade, pin to the previous version:

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.5
```

Local `config/` and `sessions/` are forward-compatible; if an incompatible RunJournal version is encountered, MAO loads old records read-only and uses the current format for new runs.
