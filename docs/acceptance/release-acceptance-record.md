# MAO v0.1.0-beta.1 Release Acceptance Record

**Execution date**: 2026-07-15

**Local environment**: Windows, Python 3.11.9, Node.js syntax check

**Privacy principle**: Do not commit real keys, private sessions, user project content, or local config.

## Six Scenario Classes

| Scenario | Execution and evidence | Token / cost | Result | Residual risk |
|---|---|---:|---|---|
| 1. Read-only explanation of unfamiliar project | Local `G:\MAO_test` historical acceptance first showed structure and selective reads; read-only policy and recon coverage regressed by `test_agent_permission.py`, `test_agent.py` | Historical private sessions not public | Pass; target project not modified | Real reports stay in ignored private sessions; not in public repo |
| 2. Fault diagnosis | Located Web start not loading `.env`; evidence loop of CLI success, Web 401, start-chain code, and post-fix Web real request | Post-fix: see `real-provider-smoke.json` | Pass; root cause fixed with regression | Provider may still return 401 on key expiry or upstream change |
| 3. Small feature change | Implemented unified context budget and Web observability; browser screenshots, 63 targeted tests, 497 full regression | Automated tests do not call models | Pass | Token counting still conservative for non-OpenAI tokenizers |
| 4. Dual-model collaboration | `python -m scripts.real_collaboration_smoke`; GLM and Kimi parallel read-only Workers | Input 428, output 200, cost `$0.000628` | Pass; 0 tool calls, 0 project writes, 2 isolated artifacts | Manual paid smoke; not auto-run in CI |
| 5. 401/429/interrupt/Reviewer reject | Real Coding Plan 401 fixed then succeeded; `test_connection_test.py`, `test_gateway_failover.py`, `test_reviewer.py` cover failure closure | Real success requests in JSON; error paths mocked | Pass | Real 429 and mid-stream interrupt not stably forceable; deterministic mocks used |
| 6. Long-session compaction recovery | `python -m scripts.context_benchmark`; large tool output, one compaction, Session save and restore | 3,919 -> 796 estimated tokens; 0 Provider calls | Pass; 39 -> 8 messages, critical fact retention 100% | Offline deterministic summary; real summary quality and triple compaction are later full baseline |

Structured evidence:

- [`context-benchmark.json`](context-benchmark.json)
- [`real-provider-smoke.json`](real-provider-smoke.json)
- [`real-collaboration-smoke.json`](real-collaboration-smoke.json)
- [`../assets/webui-chat-context.png`](../assets/webui-chat-context.png)
- [`../assets/webui-provider-context-config.png`](../assets/webui-provider-context-config.png)
- [`../assets/mao-beta-demo.gif`](../assets/mao-beta-demo.gif)

## Release Engineering Gates

- Local full tests: `497 passed, 1 warning`.
- Python compileall, JavaScript syntax, and `git diff --check`: pass.
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- `python -m build`: wheel and sdist built successfully.
- `twine check dist/*`: both artifacts pass.
- Isolated venv: install, `mao --version`, `mao-ui --help`, and minimal real Provider request pass; temp directory cleaned.
- WebUI: `http://127.0.0.1:8128/chat` healthy; budget panel data complete; browser console free of warnings/errors.
- WebUI long results: headings, bold, lists, and Markdown tables readable; browser measured message area `scrollWidth == clientWidth == 955px`; no horizontal overflow.
- README demo: 60s, 960x540, ~3 MB; real read-only project check covering 6 successful tool calls and engineering evidence panel.

## 2026-07-16 Re-Verification

- Local full tests re-check: `497 passed, 1 warning`.
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- gitleaks `8.24.3` local scan of all 29 commits: `no leaks found`.
- CI workflow hardening: `defaults.run.shell: bash`; security job uses open-source gitleaks binary (avoids private-repo `gitleaks-action` license blocking).

## Remote CI (2026-07-16)

- Run: https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29469886664
- Commit: `a819879`
- Result: **all successful**
  - ubuntu-latest / Python 3.11
  - ubuntu-latest / Python 3.12
  - windows-latest / Python 3.11
  - windows-latest / Python 3.12
  - security (pip-audit + gitleaks)

## Release Gate Status

Minimum release gates all passed. `v0.1.0-beta.1` GitHub Release may be created.

Full Context 6 multi-window, triple compaction, and real summary quality benchmarks are Beta follow-ups; they do not block the current minimum release gate but must not be advertised as complete.

Repo public-visibility changes are not automatic; require separate owner confirmation.

## v0.1.0-beta.4 Release Acceptance (2026-07-18 to 2026-07-19)

**Status**: Local and remote release gates passed; owner confirmed Tag and GitHub pre-release creation.

### Stability and Context

- Full test suite: `722 passed, 1 warning`; locally split by command host limits into core `705`, real browser `12`, stability replay `4+1`; sum matches collected total. Only warning is Starlette/httpx upstream deprecation.
- `python scripts/replay_smart_mining.py`: normal fixture completed; corrupted Mock and missing-route fixtures blocked; Provider calls 0.
- `python scripts/bench_compaction.py`: 32K, 64K, 128K, 200K each with three compactions pass; marked critical fact retention all 1.0; Provider calls 0.
- B4.3–B4.6 resume confirmation, L0/L1/L2 compaction, incremental project index, and Reviewer restricted/full input modes are all in full regression.

### Distribution and Security Gates

- `python scripts/verify_distribution.py`: wheel/sdist content contract, `twine check`, clean venv dependency install without inheriting system packages, empty-dir CLI and Web `/health` all pass.
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- gitleaks 8.24.3: official download SHA-256 verified; 60 historical commits, current tracked diff, and new `src`, `scripts`, `tests`, `docs`, and permission examples show no leaks.
- Python compileall, `src/ui/static/js/app.js` and `chat.js` syntax checks, `git diff --check` all pass.
- Version: `pyproject.toml` and `src/version.py` both `0.1.0b4`; `python run.py --version` prints `MAO 0.1.0b4`.

### 2026-07-19 Pre-Release Diff Review

- Fixed permission request lifecycle leak, unknown ID accept, Web same-session concurrent write, and mode persistence overwrite.
- Fixed resume record completed/incomplete plan contradiction, native tool block compaction entity loss, plain-text fallback masquerading as JSON artifact.
- Reviewer invalid field types no longer crash or mis-judge; failed parse still retains usage; collaboration subtask cap is 24.
- Frontend closure and browser gates added dependency structure, cross-root resources, HTTP status, full viewport, and server inline-code checks; offline replay failure gate stays blocked.
- Today-reported Provider confirmation facts apply only to their own run; gitleaks CI install adds official checksum verification.

### Remote Release Gate

- B4 code, tests, and release docs reviewed, committed, and pushed.
- First CI exposed cross-platform path asserts and Windows browser timeouts; fix commit `c0caecb`.
- [CI 29672684859](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29672684859) Windows/Ubuntu × Python 3.11/3.12 and security job all passed.
- Owner explicitly authorized creating `v0.1.0-beta.4` Tag and GitHub pre-release.

Tag points at final release-docs commit; GitHub pre-release uses immutable Release Notes in the repo.

## v0.1.0-beta.5 Release Acceptance (2026-07-21)

**Status**: Local release gates passed; Tag and GitHub pre-release await owner confirmation (not automatic).

### Stability and Context

- Full test suite: `799 passed, 1 warning`; only warning is Starlette/httpx upstream deprecation.
- `python scripts/benchmark_engineering.py`: three strategies (`fixture-fixed-single`, `fixture-auto-route`, `fixture-multi-model`) × six task classes × three repeats = 54 synthetic results, stable, signature-consistent, Provider calls 0, data tagged `synthetic_contract`.
- B5.1–B5.3, B5.5 reproducible benchmarks, execution-depth contract, explainable routing, and adversarial testing are in full regression.

### Distribution and Security Gates

- `python scripts/verify_distribution.py`: wheel/sdist content contract, `twine check`, clean venv dependency install without inheriting system packages, empty-dir CLI and Web `/health` all pass.
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- gitleaks 8.24.3: local Windows cannot download binary (auto mode refuses external download); authoritative secret scan remains remote CI job; record result after push.
- Python compileall, `src/ui/static/js/app.js` and `chat.js` syntax checks, `git diff --check` all pass (LF/CRLF line-ending normalization notes only; no whitespace errors).
- Version: `pyproject.toml` and `src/version.py` both `0.1.0b5`; `python run.py --version` prints `MAO 0.1.0b5`.

### Release Closure Scope

- Model catalog single-source audit pass: CLI and Web presets both take values via `BUILTIN_MODELS[alias].to_model_data()`; fixed small CLI `ark` Coding Plan preset hardcoding `glm-ark` away from catalog; added `test_preset_models_are_sourced_from_catalog` anti-drift regression.
- Public benchmark reproducibility: `benchmarks/engineering_v1/README.md` and `suite.yaml` record source, run commands, `data_policy`, and `synthetic_contract` tags; sdist includes full task projects and run scripts.
- CHANGELOG `[Unreleased]` converted to `[0.1.0-beta.5] - 2026-07-21` with new `[Unreleased]` pointing at beta.6; added `docs/RELEASE_NOTES_v0.1.0-beta.5.md`; README badge and status paragraph updated.

### Remote Release Gate

- B5.6 commit sequence: `814bec9` (catalog single-source fix), `6a496fb` (version and release docs), `737ac8e` (gitignore and build fixture fix), `6f95f27` (record CI green).
- B5.6 review found `cbcf056` (B5.5) remote CI actually failed and was previously unrecorded: `build/` gitignore rule hid benchmark `tasks/build/` fixtures so files were uncommitted; CI failed while local tests passed. `737ac8e` anchored the rule as `/build/` and restored fixtures.
- [CI 29829436563](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29829436563) Windows/Ubuntu × Python 3.11/3.12 and security job (pip-audit, gitleaks 8.24.3) all passed; `6f95f27` [CI 29830024005](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29830024005) also passed.
- Real paid Provider calls: none during unattended acceptance; prior `multi-model` private live smoke does not count toward public release.
- Owner confirmed creating `v0.1.0-beta.5` Tag and GitHub pre-release.

Tag points at final release-docs commit `6f95f27`; GitHub pre-release uses immutable Release Notes in the repo: <https://github.com/Wanbinyu/multi-agent-orchestrator/releases/tag/v0.1.0-beta.5>.

## v0.1.0-beta.6 Release Acceptance (2026-07-21)

**Status**: Local and remote release gates passed; owner confirmed Tag and GitHub pre-release creation.

### Stability and Features

- Full test suite: `853 passed, 1 warning`; only warning is Starlette/httpx upstream deprecation.
- B6.1–B6.5 Plugin API v0 contract, manager, CLI, example plugin, and Web visibility are in full regression (isolation rollback, incompatible reject, zero change with no plugins, idempotent load, shutdown unregister).

### Distribution and Security Gates

- `python scripts/verify_distribution.py`: builds MAO wheel/sdist and example plugin wheel; `twine check` all three; clean venv installs MAO then example plugin; `mao plugin list` shows `mao-wordcount`, `mao plugin enable` writes `config/plugins.yaml`, then runtime singleton `load_plugins` -> run `word_count` (`字符数：11`) -> `shutdown_plugins` (tool unregistered) end-to-end pass.
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- gitleaks 8.24.3: local Windows cannot download binary; authoritative scan is remote CI job; security job passed.
- Python compileall, `app.js`/`chat.js` syntax checks, `git diff --check` all pass.
- Version: `pyproject.toml` and `src/version.py` both `0.1.0b6`; `python run.py --version` prints `MAO 0.1.0b6`.

### Release Gates

- Independent example plugin discover/enable/execute/shutdown in wheel env: `verify_distribution.py` pass.
- Incompatible API version explicitly refused: B6.2 unit tests + manager compatibility decision.
- Plugin exceptions do not corrupt Session/tool registry/plugin-free startup: B6.2 isolation rollback tests.
- Plugin permissions visible in CLI/Web + disabled by default, require explicit enable: `mao plugin list` + `/api/plugins` + chat "Plugins" tab + empty default `config/plugins.yaml`.

### Remote Release Gate

- B6.6 commit sequence: `580c101` (B6.1), `96a2d7d` (B6.2), `4d2ce17` (B6.3), `99503c8` (B6.4), `00fb5ce` (B6.5), `998ea25` (B6.6 release candidate), `6de8531` (record CI green).
- [CI 29841673789](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29841673789) Windows/Ubuntu × Python 3.11/3.12 and security job (pip-audit, gitleaks 8.24.3) all passed; `6de8531` [CI 29842169141](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29842169141) also passed.
- Real paid Provider calls: none during unattended acceptance; beta.6 does not require a real model.
- Owner confirmed creating `v0.1.0-beta.6` Tag and GitHub pre-release.

Tag points at final release-docs commit `6de8531`; GitHub pre-release uses immutable Release Notes in the repo: <https://github.com/Wanbinyu/multi-agent-orchestrator/releases/tag/v0.1.0-beta.6>.

## v0.1.0-beta.7 Release Acceptance (2026-07-21)

**Status**: Security patch; local and remote release gates passed; owner confirmed Tag and GitHub pre-release creation.

### Security Fix

- P0: `run_command` allowed `python -c`/`node -e`/`node --eval`/`node -p`/`node --print` interpreter inline code execution (prefix allowlist pass + no inline check; could read `.env`/out-of-bounds write/bypass `permission_rules`). Fix `74e1829`: `_has_inline_interpreter_code` preflight rejects; `python -c` only rejected when no `-m` (avoids false-rejecting `python -m pytest -c config`). `readonly` sessions were unaffected.
- No functional change; security fix only.

### Distribution and Security Gates

- Full test suite: `856 passed, 1 warning` (only warning Starlette/httpx upstream deprecation).
- `python scripts/verify_distribution.py`: wheel/sdist + example plugin wheel, clean venv, example plugin discover/enable/execute/shutdown pass.
- `pip-audit -r requirements.txt`: no known vulnerabilities.
- gitleaks 8.24.3: remote CI security job passed.
- Python compileall, `app.js`/`chat.js` syntax checks, `git diff --check` pass.
- Version: `pyproject.toml` and `src/version.py` both `0.1.0b7`; `python run.py --version` prints `MAO 0.1.0b7`.

### Remote Release Gate

- Commit sequence: `74e1829` (P0 fix), `49267ba` (beta.7 release docs).
- [CI 29878487250](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29878487250) (`74e1829`) and [CI 29881111078](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29881111078) (`49267ba`) Windows/Ubuntu × Python 3.11/3.12 and security job all passed.
- Real paid Provider calls: none during unattended acceptance.
- Owner confirmed creating `v0.1.0-beta.7` Tag and GitHub pre-release.

Tag points at release-docs commit `49267ba`; GitHub pre-release uses immutable Release Notes in the repo: <https://github.com/Wanbinyu/multi-agent-orchestrator/releases/tag/v0.1.0-beta.7>.
