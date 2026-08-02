# v0.1.0-beta.5 Execution Checklist

**Status**: B5.1–B5.3 completed; B5.4 offline infrastructure completed, real evaluation paused; B5.5 adversarial testing and local-model routing contracts completed

**Goal**: Use public, reproducible data to show when a single model is more appropriate and when multi-model collaboration improves completion rate or lowers cost, then harden conclusions into bounded, explainable, fallback-safe routing policy.

**Release baseline**: `v0.1.0-beta.4`

## 0. Execution principles

- Establish measurement contracts before changing routing behavior; routing implementation must not reverse-define success metrics.
- Default benchmarks must be offline, redacted, and zero Provider calls; real paid comparisons need separate owner confirmation of models, counts, and cost caps.
- Single-model and MAO use the same task input, workspace snapshot, verification gates, and completion criteria.
- Public data must not include public coding-benchmark original problems, private projects, secrets, or non-redistributable content.
- Advance only one slice at a time; keep failure results and “multi-model has no advantage” results as well.

## 1. B5.1 Reproducible benchmark contract and offline harness

- [x] Define task Schema: category, input, fixture, allowed modifications, verification commands, success criteria, risk, and source.
- [x] Cover six minimal task types: Q&A, diagnosis, small change, build, review, and migration.
- [x] Define result Schema: input/output tokens, estimated cost, tool-call count, duration, completion rate, mis-modification rate, and verification pass rate.
- [x] Single-model and MAO share the same runner, isolated workspace, and deterministic acceptor.
- [x] Default fixture policy enables zero-cost CI runs and verifies that repeated runs do not pollute the next round.
- [x] Output machine-readable JSON and concise Markdown reports retaining task, run, and evidence provenance.

### B5.1 completion gates

- [x] Same fixture runs at least three times in a row with stable success judgments and metric fields.
- [x] Failure, timeout, empty output, and out-of-bounds modification all enter failure results and are not masked by averages.
- [x] Harness does not read real keys, call paid Providers, or depend on absolute paths on the dev machine.
- [ ] Windows/Ubuntu, Python 3.11/3.12 CI passes (local done; waiting for remote CI after push).

### B5.1 completion notes (2026-07-19)

- `src/core/engineering/benchmark.py` adds versioned task/result Schema, strategy protocol, isolated workspace, deterministic acceptance, repeat signatures, aggregate metrics, and JSON/Markdown reports.
- `benchmarks/engineering_v1/` provides six programmatic redacted tasks; verification commands are limited to in-project whitelist executables; absolute paths, parent dirs, interpreter inline code, and symlink fixtures are rejected.
- `fixture-single` and `fixture-mao` each run three times through the same harness, 36 results total: all pass, signatures stable, mis-modification rate 0, Provider calls 0. Data is explicitly marked `synthetic_contract` and must not be used to advertise real model advantages.
- Wheel includes the benchmark core module; sdist includes the public suite, run script, and six task projects. `twine check` and distribution archive contract pass; the source package can reproduce the offline benchmark directly.
- Failure contracts cover out-of-bounds modification, empty response, timeout, Provider-call leak, unstable metrics, illegal paths, and unsafe commands; targeted tests `13 passed`.
- Expanded regression split by host time limit into core `718`, real browser `12`, stability replay `5`, total `735 passed, 1 warning`. Only warning remains Starlette/httpx upstream deprecation.
- CI adds `Offline engineering benchmark gate`; remote matrix results can only be recorded after push.

## 2. B5.2 Execution-depth contract

- [x] Define tool, Worker, Reviewer, context, and verification budgets for `fast`, `standard`, and `deep`.
- [x] Simple tasks default to not starting Workers; high-risk tasks cannot bypass deterministic verification with `fast`.
- [x] Explicit user choice overrides automatic suggestion; actual depth and reason are written to RunJournal.

### B5.2 completion notes (2026-07-19)

- `ExecutionDepthDecision` stores user request, automatic suggestion, actual depth, source, reason, and budget together; RunJournal upgrades to v4; old records still load.
- `fast` limits 3 main-Agent tool rounds, 50% context budget, and disables Workers; `standard` limits 6 rounds, 75% context, 2 Workers; `deep` limits 8 rounds, full context, 4 Workers. When collaboration occurs, `standard/deep` must both enter Reviewer.
- CLI adds `/depth auto|fast|standard|deep`; Web provides the same session-preference API; Web engineering records show request, suggestion, actual depth, and budget.
- Explicit choice overrides automatic suggestion; small changes can use `fast` to lower tool and Worker overhead but still keep the original task’s `standard` verification gates. High risk and `deep` contracts form a non-lowerable safety floor; real multi-file, dependency, or new-directory writes re-evaluate and escalate to `deep` without expanding original tool permissions.
- Execution depth constrains context-compaction frequency, main Agent/Worker tool rounds, Worker concurrency, and change-verification floor. Full tests `749 passed, 1 warning`; B5 engineering benchmark 36/36 stable, smart-mining positive/negative replay, JavaScript/Python syntax, diff hygiene, and distribution acceptance all pass with Provider calls 0. Only warning is Starlette/httpx upstream deprecation.

## 3. B5.3 Explainable model routing

- [x] Routing inputs use only task type, capability truth, price, context, health, and user constraints.
- [x] Unverified capabilities must not drive automatic upgrades; cost savings must not be claimed when price is unknown.
- [x] On routing failure, fall back to the user-specified model and bound retries and upgrade counts.
- [x] CLI/Web show concise reasons; full decisions go to RunJournal.

### B5.3 completion notes (2026-07-19)

- `ModelRouter.route()` deterministically evaluates task type, execution depth, explicit capability status, price source, safe context budget, health cooldown, local models, and user constraints before Provider calls; runtime failover remains a separate layer and cannot reverse-write routing reasons.
- Automatic routing selects at most one candidate model. Only `supported` capabilities may trigger upgrades; legacy `capabilities` lists still count as `unverified` when metadata source is unverified. When price source is unknown, `price_comparison=unknown`, `savings_claim_allowed=false`; savings claims must not be emitted.
- Session default is `auto`; CLI `/routing fixed` and Web session API can lock the user’s primary model. When an auto candidate hits a switchable failure, Gateway prefers falling back to the user primary model, then follows the existing failover contract; fatal errors such as auth and illegal request still do not blindly switch models.
- RunJournal upgrades to v5: event summaries only show selected model, source, and concise reason; full records keep candidate eligibility, capability status, context, health, price, scores, and elimination reasons. CLI/Web both show actual model and reason.
- Full tests `763 passed, 1 warning`; B5 benchmark 36/36 stable, smart-mining positive/negative replay, JavaScript/Python syntax, diff hygiene, and distribution acceptance all pass with Provider calls 0. Only warning is Starlette/httpx upstream deprecation.

## 4. B5.4 Single-model vs multi-model comparison

- [x] **Phase start reminder**: Project owner has been told “real MAO capability testing is starting now”; do not call real Providers until models, counts, cost caps, and public scope are confirmed.
- [x] Same harness has fixed independent control variables for fixed single-model, auto-route, and multi-model collaboration; offline 54 synthetic results pass.
- [ ] After authorization, run all three real strategies on the same harness.
- [ ] Produce at least one public token/cost advantage case.
- [ ] Produce at least one multi-model completion-rate advantage case, or explicitly record task types that should not use multi-model.
- [x] Report Schema independently records model set, routing, execution depth, and collaboration strategy; synthetic data is explicitly marked `synthetic_contract`.
- [x] Complete non-interactive `mao benchmark-agent` entry and Harbor `BaseInstalledAgent` adapter recording traces, tokens, cost, models, and engineering audit.
- [ ] After authorization, first run one serial Terminal-Bench/Harbor task; expand only after checking verifier, mis-modification, and repeat stability.
- [ ] Evaluate SWE-bench Lite/Verified only after B5.4 is stable; Aider Polyglot is only a code-edit supplement, not a conclusion about MAO’s overall Agent capability.

### External evaluation boundaries

- There is currently no trusted “upload MAO once for automatic composite scoring” service; the standard flow is to adapt the Agent interface, run task sets in Docker/isolated environments, and submit traces and results.
- Official entry points: Terminal-Bench <https://www.tbench.ai/>, Harbor run docs <https://harborframework.com/docs/running-tbench>, SWE-bench <https://www.swebench.com/>, Aider Leaderboard <https://aider.chat/docs/leaderboards/>.
- Terminal-Bench adapter does not interrupt B5.2–B5.3; before cost confirmation, only complete the adapter, offline contracts, and a few mock/fixture validations—no paid Provider calls.

### B5.4 offline infrastructure notes (2026-07-19)

- Three profiles × 6 task types × 3 runs = 54/54 synthetic results pass; stability signatures consistent; Provider calls 0.
- `mao benchmark-agent` unit-tested to use production Agent stream, restricted workspace, new Session, strategy constraints, and machine-readable results.
- Current full regression `787 passed, 1 warning`; wheel/sdist, `twine check`, clean install, CLI and Web health distribution acceptance pass. Only warning remains Starlette/httpx upstream deprecation.
- Harbor adapter aligned to official `0.20.x` `BaseInstalledAgent` source contract; current dev machine has only Python 3.11 while Harbor `0.20.x` requires 3.12, so real import/Docker runs remain the first post-authorization smoke acceptance item.

### B5.4 first real smoke notes (2026-07-19, private)

- Strategies: fixed single-model `glm-ark`, auto-route/multi-model `glm-ark + kimi-for-coding`; task is public programmatic `build-health-module`, serial, once each.
- First run found live-smoke script did not load `.env` like the `mao` entry; all 3 strategies failed at auth with token/cost 0. Fixed with `.env` load, failed-attempt counting, and fail-fast.
- `fixed-single` external verifier passed: 3 Provider calls, input/output `2857/431`, cost `$0.003288`, out-of-bounds modifications 0. MAO still marked `blocked` internally because the public small fixture’s verifier does not satisfy the full high-risk build engineering verification gates.
- `auto-route` both rounds used only `glm-ark`, matching the “unverified capabilities do not auto-upgrade” contract; but discovered that `project_tree` default index wrote `config/memory/file_index.yaml` into the tested workspace and was correctly rejected by the harness as out-of-bounds modification.
- Index storage was changed so Agent/Worker inject the evaluation state directory via tool runtime context; related offline regressions pass; still needs confirmation on the next real smoke.
- Owner raised cumulative Provider attempt cap from 20 to 35; results remain `private`; cost cap stays `$0.20`.
- After index redirect, `auto-route` passed external verifier; actual model still only `glm-ark`, matching the conservative no-auto-upgrade contract for unverified capabilities.
- `multi-model` successively exposed and fixed: top-level task-array parsing, model-output role aliases, list-form acceptance criteria, and software tasks wrongly using creative Workers. Related behaviors were added to offline regressions.
- Third-round `multi-model` exposed a stop-gate that only aggregated after the full round: remaining authorization was 8 attempts but 13 actually occurred, cumulative **40/35**, cumulative real cost `$0.032453`. All real calls were stopped after discovery.
- Call gate changed to atomic pre-reserve before each Provider network request; the N+1st attempt is rejected before the request is sent; concurrent Workers share the same thread-safe cap; gateway also accumulates successful and failed attempts. Fix passed mock/offline tests but was not re-verified with real Providers because authorization was exhausted.
- Current `multi-model` is still not accepted: latest report `bench-fb6c0b3bf4d0` actually used only `glm-ark` and external verifier failed; dual-model effect must not be claimed from this.

## 5. B5.5 Experimental capabilities

- [x] Adversarial testing Worker is enabled only in the experimental tier; tries to refute implementation results and records evidence.
- [x] Local/Ollama models may be zero-marginal-cost candidates, but health checks and capability gates are not lowered.
- [ ] When expanding the model catalog, continue official sources, `unverified` fallback, and CLI/Web single source of truth.

### B5.5 completion notes (2026-07-20)

- Session adds default-off `adversarial_testing`. Read-only `AdversarialTester` runs only when user explicitly enables it, actual execution depth is `deep`, intent is `change/build`, all collaboration Workers succeed, and deterministic completion audit already passed; if deterministic audit already blocked, skip to avoid wasting tokens.
- Adversarial role receives only original requirements, plan, file/acceptance info, real command evidence, and verification gates—not Worker self-narration body—and has no tools or write permissions. Output uses strict JSON parse, field-type checks, and length/count caps; abnormal or invalid output degrades to `inconclusive`.
- `refuted` can only downgrade a prior complete conclusion to `blocked`, never upgrade a failure; `inconclusive` only records residual risk. Conclusion, suggested checks, model/usage, and Evidence write to RunJournal; suggested checks are explicitly marked “not executed.”
- CLI adds `/adversarial on|off`; Web adds session-level experiment switch and `adversarial_complete` status; mid-run changes return 409. Default off, refresh-persisted, 320/390/1280px layouts and browser console error-free all verified.
- Local/Ollama candidates may be selected by `fast` at zero estimated cost when verified capability, health, and context all pass; zero-cost bonus cannot bypass health cooldown, capability truth, or context gates. When `deep build` needs reasoning, local models with only coding capability are rejected and a qualified cloud model is chosen.
- Full regression `798 passed, 1 warning`; 54/54 offline engineering benchmarks stable, Provider calls/attempts 0; Python/JavaScript syntax, diff hygiene, and distribution acceptance pass. Only warning remains Starlette/httpx upstream deprecation.

## 6. B5.6 Release closeout

- [x] Full tests, security scans, distribution acceptance, and clean install pass.
- [x] Benchmark task sources, generation method, run commands, and results are publicly reproducible.
- [x] CHANGELOG, Release Notes, version number, and upgrade notes complete.
- [x] Tag and GitHub pre-release created after owner confirmation (`v0.1.0-beta.5` points to `6f95f27`).

### B5.6 completion notes (2026-07-21)

- Model-catalog single source of truth audit: CLI (`provider_presets.py`, `agent_setup.py`) and Web (`src/ui/presets/builtin/*`) both take values via `BUILTIN_MODELS[alias].to_model_data()`; found and fixed a small drift where CLI `ark` Coding Plan preset hard-coded `glm-ark` off the catalog so it matches Web `ark-coding` and other presets. Added `test_preset_models_are_sourced_from_catalog` anti-drift regression.
- Public benchmark reproducibility: `benchmarks/engineering_v1/README.md` and `suite.yaml` record task source (`programmatic MAO fixture`), run command (`python scripts/benchmark_engineering.py`), `data_policy` (no public original problems/private projects/secrets/Provider calls), and `synthetic_contract` mark; sdist includes full task projects and run script.
- Version: `src/version.py`, `pyproject.toml`, `tests/test_version.py` all to `0.1.0b5`; `python run.py --version` prints `MAO 0.1.0b5`.
- Docs: CHANGELOG `[Unreleased]` becomes `[0.1.0-beta.5] - 2026-07-21` with new `[Unreleased]` pointing at beta.6; add `docs/RELEASE_NOTES_v0.1.0-beta.5.md` (Highlights, Install, Upgrade Notes, Verification, Known Limitations); README badge and status section updated.
- Verification: full regression `799 passed, 1 warning` (only warning Starlette/httpx upstream deprecation); `pip-audit -r requirements.txt` no known vulns; `python -m compileall`, `node --check` (app.js/chat.js), `git diff --check` pass; `python scripts/verify_distribution.py` builds wheel/sdist, checks archive contract, clean venv install, empty-dir CLI and Web `/health` pass.
- Security scan boundary: gitleaks 8.24.3 cannot download binary on local Windows (auto mode rejects external download); authoritative secret scan is the remote CI job, already passed in [run 29829436563](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29829436563).
- During re-review found `cbcf056` (B5.5) remote CI actually failed but was not recorded earlier: `build/` gitignore hid the benchmark `tasks/build/` fixture so files were uncommitted—CI failed while local tests passed. `737ac8e` anchored the rule to `/build/` and restored `tasks/build/project/{README.md,verify.py}`; remote CI fully green (Windows/Ubuntu × Python 3.11/3.12 and security job).
- Real Provider calls: no paid Provider during unattended acceptance; prior `multi-model` private live smoke is not counted in the public release and is not used to claim any model advantage.
- Tag and GitHub pre-release: created after owner confirmation. `v0.1.0-beta.5` points to `6f95f27`; GitHub pre-release uses in-repo `RELEASE_NOTES_v0.1.0-beta.5.md`.

## 7. Current next steps

B5.6 release closeout complete; `v0.1.0-beta.5` published (Tag + GitHub pre-release). Next enter `beta.6` Plugin API v0. B5.4 real `multi-model` evaluation remains separately paused; private smoke may continue only after the owner gives a new cumulative attempt boundary. See [`B5.4-real-capability-benchmark-handbook.md`](../../B5.4-real-capability-benchmark-handbook.md).
