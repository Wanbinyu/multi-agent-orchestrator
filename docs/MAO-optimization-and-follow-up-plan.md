# MAO Optimization and Follow-up Development Plan

**Status**: Current execution entry

**Last updated**: 2026-07-25

**Baseline**: `v0.1.0-beta.7`; O1 documentation consolidation and O2 U4 schema examples landed; **O3 Provider compatibility matrix and security boundaries completed**; real Provider evaluation remains paused.

## 1. Goals

Before adding more features, first tighten MAO into an explainable, verifiable, maintainable Beta product:

- Users can install, configure a Provider, and complete one real project task.
- CLI, Web, and headless interfaces give consistent status, event, and error semantics for the same run.
- Tool calls, file changes, commands, verification, and completion decisions all have traceable Evidence.
- Do not over-claim OS/container-level sandboxing, real Provider comparisons, or external user validation when those are not implemented.
- New features must have clear user scenarios, acceptance criteria, and regression tests—not merely more model roles or config knobs.

## 2. Current baseline and clear lagging items

### Completed and should stay stable

- Provider configuration, model catalog, CLI/Web chat, and multi-model Worker collaboration.
- `auto`, `approve`, `readonly` permission modes, plus Plan, Evidence, VerificationGate, CompletionAudit, and RunJournal.
- Context budget, compaction, project scouting, command verification, frontend smoke, engineering benchmark, and Plugin API v0.
- U4 `plain`, `json`, `streaming-json` output; JSON/JSONL already cover plan, model, tool, file change, command, verification, approval, usage, error, and end status.
- Documentation is split into current entry points, usage guides, release records, and `docs/archive/` historical archive.

### Needs optimization or re-verification

1. **Documentation source of truth**: Historical Beta checklists, old comparisons, and old stability plans must not remain current-task entry points; living status is maintained only in the doc index, project progress, product roadmap, and this document.
2. **U4 event boundaries**: Complete unified semantics for session compaction, recovery, and long-task interruption events; confirm JSON vs JSONL schema, order, exit codes, and version compatibility policy.
3. **Provider compatibility**: Build a matrix of capability, context window, structured tools, streaming, vision, price source, verification date, and known limits for Providers actually in use; `unverified` must not participate in capability or savings claims.
4. **Real-task Evidence**: Offline fixtures only prove contracts and regression stability; they cannot replace external user installs, real project tasks, and real model comparisons.
5. **Security boundary wording**: Tools and plugins still run with host process privileges; permission rules are an authorization control plane, not an OS/container sandbox. Keep consistent wording in README, guides, and UI.
6. **Long-task documentation**: The context plan remains a technical direction, but stage status and version references need re-checking against U4, B5.4, and v0.2.0 criteria.

## 3. Optimization order

### O1 Documentation and contract consolidation

**Scope**: Finish broken-link fixes; mark status and update time on every living document; archive history as read-only; establish minimal schema examples and change rules for U4 events.

**Acceptance**: All living Markdown links in the repo are valid; no current entry points to moved documents; `docs/README.md` explains each document class; U4 schema can be jointly validated by tests and examples.

### O2 U4 and run observability

**Scope**: Unify `mao run` event names, required fields, timestamps, run ID, error/exit status, and end events; ensure concurrent Worker JSONL does not interleave, lose, or forge usage. Session-level compaction, resume, and blocked belong to Session/Web API and must not be mixed with one-shot CLI JSONL.

**U4 event schema example** (minimal verifiable version, JSON Schema style, usable for docs or code validation):

```json
{
  "type": "object",
  "required": ["type", "ts", "run_id", "data"],
  "properties": {
    "type": { "type": "string", "enum": ["run", "plan", "model", "tool", "command", "file_change", "verification", "approval", "usage", "error", "cancel", "end"] },
    "run_id": { "type": "string" },
    "ts": { "type": "string", "format": "date-time" },
    "data": { "type": "object" }
  }
}
```

`end.data` must include `status` (`completed`, `failed`, or `cancelled`), `exit_code`, and `elapsed_ms`; `usage` and `error` events provide in-run billing and failure information. `cancel` only means pre-execution approval was rejected, ending with exit code `130`.

**Acceptance**: Offline tests cover success, failure, cancel, no Provider, and multi-thread events; `json` is readable by a standard JSON parser; every `streaming-json` line is independent JSON; all events share the same `run_id`; `end` appears last and exit status is consistent.

### O3 Provider compatibility matrix and security boundaries — ✅ completed (2026-07-25)

**Scope**: Cover Providers actually used by the project first, then expand presets; bind capability status and price sources to the model catalog; update security docs, plugin guide, and quick start to clarify same-process plugin risk and the absence of an OS sandbox.

**Deliverables**:
- [`Provider-compatibility-matrix.md`](Provider-compatibility-matrix.md): template tables, model matrix, error codes, security boundaries, update rules.
- `src/models/catalog.py`: `export_compatibility_matrix()` / `is_verified_metadata_source()` / known-limit summaries.
- `tests/test_provider_matrix.py`: catalog binding, supported requires verified source, unverified cannot upgrade, complete error codes.
- Updated `SECURITY.md`, `README.md`, `QUICKSTART.md`, plugin guide, local LLM docs, `providers.yaml.example`.

**Acceptance**: Unknown capabilities default conservative; connection failure, auth failure, rate limit, and model unsupported have stable error codes; automatic routing will not select unverified capabilities; docs do not describe permission rules as a sandbox.

### O4 External users and real-task validation

**Scope**: Prepare redacted feedback templates and a minimal problem report; invite at least 10 external users to install and drive at least 5 real project tasks; resume B5.4 real evaluation only after explicit authorization of attempt count, cost, model, and publication scope.

**Landed (2026-07-28, templates and channels)**:
- GitHub Issue templates: install feedback, real-task feedback; strengthened redaction confirmation and error-code fields on Bug / Provider templates.
- [`docs/external-user-feedback-guide.md`](external-user-feedback-guide.md), [`acceptance/redacted-feedback-template.md`](acceptance/redacted-feedback-template.md).
- `scripts/sanitize_feedback_text.py` + unit tests (Key / Bearer / home-directory segment redaction).

**Still waiting on external input**: ≥10 installs, ≥5 real-task Issues; B5.4 real evaluation needs owner re-authorization.

**Acceptance**: `v0.2.0` criteria #1 and #3 have reviewable Evidence; real results are archived separately from synthetic contracts; single successes or unauthorized calls are not written as product conclusions.

### O5 Then decide product expansion

Only after O1–O4 meet acceptance gates, evaluate IDE extensions, desktop, remote execution, multi-user collaboration, team audit, and plugin ecosystem. Write a one-page decision record for each direction before a minimal prototype.

## 4. Follow-up development candidates

Retain these candidates by priority:

| Priority | Direction | Entry condition |
|---|---|---|
| P0 | U4 event schema, recovery/compaction boundaries, exit codes | O1 done with offline regression |
| P0 | Provider compatibility matrix and error semantics | At least one real Provider has authorized smoke |
| P1 | External-user install diagnostics, feedback export, and repro packages | Do not upload secrets or project content |
| P1 | Long-task benchmark and cost/completion-rate reports | Separated from real Provider results |
| P2 | IDE/desktop interaction adaptation | External users clearly request stable need |
| P2 | Remote execution, multi-user, enterprise audit | First complete permission, identity, tenant, and isolation design |

## 5. Not developing yet

- Do not start with a plugin marketplace, automatic model install, or unbounded extension mechanisms.
- Do not start with “fully automatic” permission bypass, unconfirmed writes, or unverified automatic-routing savings promises.
- Do not package path checks, Python process privileges, or plugin enable gates as container/OS sandboxes.
- Do not copy the full feature lists of OpenCode, Aider, Cline, or other products.
- Do not parallel-develop desktop, IDE extensions, and cloud services without real user feedback and run Evidence.

## 6. Completion gate for every change

Any follow-up change must leave this record:

1. Target user scenario and problems not solved.
2. Affected interfaces, events, configuration, or documentation sources of truth.
3. Targeted tests, adjacent-module regression, and necessary distribution verification.
4. Failures, unverified capabilities, permission limits, and real Provider call situation.
5. Status update in the current progress doc; completed stage materials move into `docs/archive/`.

## 7. Next execution checklist

- [x] Finish documentation link checks and keep `docs/README.md` as the sole documentation navigation (including the Provider compatibility matrix entry).
- [x] Add stable event envelopes, cancel events, concurrent JSONL atomicity, and exit-status contract tests for one-shot `mao run`; session compaction/resume/blocked remain covered by Session/Web API tests.
- [x] Update the context plan, Provider compatibility matrix, and security boundary wording (O3).
- [x] Run full tests, distribution acceptance, and Markdown link checks (2026-07-28: `912 passed, 1 warning`; distribution acceptance and local link checks for 43 living Markdown files passed).
- [x] O4 redacted feedback templates and channels (Issue templates, guide, sanitize script, 2026-07-28).
- [ ] Wait for external user feedback and new real Provider authorization; do not auto-resume paid evaluation (O4 collection phase).
- [ ] After O1–O4 complete, create separate decision documents for subsequent product directions.
