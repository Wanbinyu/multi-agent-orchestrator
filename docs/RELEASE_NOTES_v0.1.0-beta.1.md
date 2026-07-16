# MAO v0.1.0-beta.1 Release Notes

This first beta is intended for developers who want to evaluate evidence-driven, multi-model engineering workflows on a trusted local machine.

## Highlights

- Configure multiple Anthropic/OpenAI-compatible Providers and route logical model aliases.
- Work in CLI or WebUI with persistent sessions, streaming output and project-tree inspection.
- Classify read-only versus write-authorized tasks before tools run.
- Record tool evidence, verification gates and completion audit results.
- Split eligible engineering work across bounded Workers with path ownership and targeted retry.

## Install and upgrade

For a fresh environment, follow the five-minute quick start in `README.md`. Existing source users can install the package in editable mode with `python -m pip install -e ".[test]"`; private `.env` and `config/*.yaml` files remain local.

There is no migration of session or memory data in this release. Back up private runtime directories before moving between beta versions.

## Known limitations

- No container-level sandbox; local commands run with the MAO process privileges.
- Dynamic Provider model aliases may not expose the exact upstream model version or hard context limit.
- Real paid-model compatibility is manually smoke-tested and is not exercised in CI.
- Layered context compaction, persistent project summaries and full performance benchmarks are post-beta work.

## Release status

Local acceptance gates, real Provider smoke tests and the cross-platform CI matrix
(Windows/Ubuntu × Python 3.11/3.12 + security) all passed on 2026-07-16 before this tag.
