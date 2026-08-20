# MAO Documentation

This directory holds the current architecture, product direction, optimization plans, usage/extension guides, and release records. Completed or superseded stage designs live under `archive/` and are no longer mixed with current plans.

## Current architecture and direction

- [`MAO-architecture-overview.md`](MAO-architecture-overview.md): Current modules, data flow, permissions, and engineering boundaries.
- [`MAO-product-direction-and-beta-roadmap.md`](MAO-product-direction-and-beta-roadmap.md): Long-term positioning, product principles, and priorities.
- [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md): Optimization priorities, acceptance gates, and follow-up development order after documentation cleanup.
- [`project-progress-and-key-operations.md`](project-progress-and-key-operations.md): Status, commands, and recovery entry points for continuing development across devices.
- [`v0.2.0-entry-criteria.md`](v0.2.0-entry-criteria.md): Five entry criteria for a v0.2.0 release and current satisfaction status.
- [`Plugin-API-compatibility-policy.md`](Plugin-API-compatibility-policy.md): Plugin API version semantics, compatibility checks, and evolution commitments.
- [`context-extension-and-long-task-stability-plan.md`](context-extension-and-long-task-stability-plan.md): Layered compaction, project indexing, and long-task benchmark work.
- [`open-source-coding-agent-reference-plan.md`](open-source-coding-agent-reference-plan.md): License audits, absorbed contracts, and phased integration order for Grok Build, Codex, OpenCode, Aider, Cline, and related projects.
- [`P0-缩小对Claude-Code日常体感差距清单.md`](P0-缩小对Claude-Code日常体感差距清单.md): Ten daily-path P0 items vs Claude Code (single-Agent loop, bounded fix, Git/commands, context and navigation, checkpoints, default no extra collaboration, daily fixtures, CLI). No IDE/desktop/enterprise items.

Completed Beta version plans, execution checklists, old comparisons, and real-task retrospectives live under [`archive/completed-beta/`](archive/completed-beta/). They are for historical traceability only and are not current status or new-task entry points.

## Usage and extension

- [`QUICKSTART.md`](QUICKSTART.md): Quick start.
- [`migration-guide.md`](migration-guide.md): Upgrade notes from beta.3 through beta.6 and migration points toward v0.2.0.
- [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md): Provider/model capability status, error codes, and catalog-bound compatibility matrix; permission rules are application-level authorization, not an OS/container sandbox.
- [`tool-development-guide.md`](tool-development-guide.md): Extending built-in tools and third-party tools.
- [`plugin-development-guide.md`](plugin-development-guide.md): Plugin API v0 plugin development (manifest/entry point/lifecycle/permissions/examples).
- [`local-llm-integration-and-extension-points.md`](local-llm-integration-and-extension-points.md): Local model integration options.
- [`B5.4-real-capability-benchmark-handbook.md`](B5.4-real-capability-benchmark-handbook.md): Real capability evaluation operations, key injection, and result interpretation.
- [`verification-guide.md`](verification-guide.md): Local verification and troubleshooting checks.
- [`external-user-feedback-guide.md`](external-user-feedback-guide.md): O4 redacted feedback, Issue template usage, and content that must not be pasted.
- [`acceptance/redacted-feedback-template.md`](acceptance/redacted-feedback-template.md): Copy-paste offline feedback skeleton.
- [`acceptance/first-install-acceptance-checklist.md`](acceptance/first-install-acceptance-checklist.md): Empty-directory 10-minute path.

## Releases

- [`RELEASE_NOTES_v0.1.0-beta.1.md`](RELEASE_NOTES_v0.1.0-beta.1.md)
- [`RELEASE_NOTES_v0.1.0-beta.2.md`](RELEASE_NOTES_v0.1.0-beta.2.md)
- [`RELEASE_NOTES_v0.1.0-beta.3.md`](RELEASE_NOTES_v0.1.0-beta.3.md)
- [`RELEASE_NOTES_v0.1.0-beta.4.md`](RELEASE_NOTES_v0.1.0-beta.4.md)
- [`RELEASE_NOTES_v0.1.0-beta.5.md`](RELEASE_NOTES_v0.1.0-beta.5.md)
- [`RELEASE_NOTES_v0.1.0-beta.6.md`](RELEASE_NOTES_v0.1.0-beta.6.md)
- [`RELEASE_NOTES_v0.1.0-beta.7.md`](RELEASE_NOTES_v0.1.0-beta.7.md)
- [`acceptance/release-acceptance-record.md`](acceptance/release-acceptance-record.md)
- [`acceptance/first-install-acceptance-checklist.md`](acceptance/first-install-acceptance-checklist.md): Empty directory / new project 10-minute path and automation script (`scripts/first_run_acceptance.py`).

## Historical archive

- [`archive/README.md`](archive/README.md): Early architecture, completed stages, old comparisons, and release preparation process.

`acceptance/` and `archive/` are for maintainer traceability and are excluded from published source archives via `export-ignore`; contributors who clone via Git can still view the full history. New plans and current status should only update the living documents listed here, so the same facts are not maintained in multiple historical checklists.
