# MAO v0.1.0-beta.4 Release Notes

This release focuses on one outcome: multi-model engineering work should remain understandable, recoverable and verifiable across long sessions and real frontend builds.

## Highlights

- **Real-task stability gate**: natural project-build requests enter high-risk planning and multi-model collaboration; observed writes dynamically raise audit depth. Portable commands use structured cwd/argv, and frontend contracts close routes, imports, dependencies, ownership and verification evidence.
- **Controlled browser verification**: Playwright starts a bounded local server and checks login, routes, data/canvas content, console errors and desktop/mobile layout. Broken Mock login and missing-route fixtures stay blocked. The sanitized smart-mining replay runs in CI with zero Provider calls.
- **Truthful engineering reports**: CLI `/runs` and `/report session|today`, plus Web run details and delivery reports, aggregate local RunJournals without spending tokens. Reports preserve run/evidence provenance and expose role/model usage, completion, first-pass runnable, rework, misdiagnosis and token-per-delivery metrics.
- **Explicit interrupted-session recovery**: CLI `/resume` and the Web recovery banner block new work until the user continues or abandons an interrupted run. Continuation creates a new run with an unfinished-step checkpoint; completed work and existing files are never auto-replayed.
- **Layered long-context compaction**: L0 artifact references, L1 structured summaries and L2 recent full messages preserve a deterministic RunJournal checkpoint. Schema fallback, entity retention and task-relevance metrics are recorded. Offline 32K/64K/128K/200K profiles each pass three compactions with 100% marked critical-fact retention.
- **Incremental project index**: index v2 stores the project root, stable tree, symbols, summaries and SHA-256 hashes. Unchanged projects require zero content rereads; one changed file rereads only that file. Corrupt and cross-root caches rebuild safely.
- **Independent Reviewer evidence**: Reviewer defaults to `restricted`, receiving requirements, plans, files and direct engineering evidence but not Worker response bodies. Configurable `full` mode remains available, while failed Workers and deterministic audits retain veto power.
- **Grok Build behavior contracts**: persistent Plan mode, hierarchical project rules and `deny > ask > allow > session default` permission rules are integrated with MAO's multi-model Orchestrator/Worker/Reviewer flow.
- **Release-review hardening**: live permission requests are bounded and cleaned, collaboration fan-out is capped, inconsistent recovery records become blocked, native tool entities survive compaction, Reviewer JSON types are strict, frontend smoke rejects HTTP/viewport false positives, and Web prevents concurrent mutation of one session.

## Install

Install directly from the published tag:

```bash
pipx install git+https://github.com/Wanbinyu/multi-agent-orchestrator.git@v0.1.0-beta.4
mao
# or
mao web
```

Python 3.11 or 3.12 is required. Runtime configuration, keys, sessions and indexes remain local and must not be committed.

## Verification

- Complete local test collection: `722 passed, 1 warning`; the only warning is an upstream Starlette/httpx deprecation notice. The collection was split into core (705), real-browser (12), and replay (4+1) groups to stay within the local command host's time limit; CI runs the complete suite normally.
- `scripts/replay_smart_mining.py`: positive build completes; broken Mock and missing route remain blocked; Provider calls are zero.
- `scripts/bench_compaction.py`: four context profiles, three compactions each, marked critical-fact retention 1.0; Provider calls are zero.
- Distribution acceptance builds wheel/sdist, checks archive contents, installs dependencies in a clean virtual environment without inherited system packages, and verifies clean CLI plus Web `/health`.
- `pip-audit -r requirements.txt` reports no known vulnerabilities. The checksum-verified gitleaks 8.24.3 scan reports no leaks across 60 historical commits, the tracked diff, or the new source, scripts, tests, documentation and permission example.
- Python compileall, JavaScript syntax checks and diff hygiene pass locally.
- Real paid Provider calls were not made during unattended acceptance.
- [Remote CI 29672684859](https://github.com/Wanbinyu/multi-agent-orchestrator/actions/runs/29672684859) passed on Windows/Ubuntu with Python 3.11/3.12 plus the security job. The release fix pins the Playwright Chromium runtime and keeps diagnostic paths platform-independent.

## Known Limitations

- Tool execution is constrained by MAO rules but is not container- or OS-sandboxed.
- Provider compatibility still varies, especially native tool use, dynamic model aliases and upstream context limits.
- The layered compaction benchmark validates deterministic retention markers; real-model summary quality still needs controlled Provider smoke.
- The project index uses stat metadata as its zero-read fast path; content hash is recalculated when metadata changes.
- `restricted` Reviewer mode validates direct evidence but cannot reconstruct creative Worker prose; use `full` only when that tradeoff is intentional.
