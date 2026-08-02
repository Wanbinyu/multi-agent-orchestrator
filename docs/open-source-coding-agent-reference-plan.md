# Open-Source Coding Agent Reference and Adoption Plan

**Audit date**: 2026-07-18

**Principles**: MAO absorbs validated behavior contracts; it does not pile features by hype. Prefer independent implementation; copy source only when direct reuse clearly reduces risk, and retain original license, copyright, NOTICE, and modification notes.

## 1. Candidate Projects and Conclusions

| Project | Audited commit | License | Mature ideas | Treatment for MAO |
|---|---|---|---|---|
| [Grok Build](https://github.com/xai-org/grok-build) | `98c3b2438aa922fbbe6178a5c0a4c48f85edc8ce` | Apache-2.0 | Plan/permissions/rules, headless JSON/JSONL, sandbox, background tasks, verification sub-agent | Base contracts implemented; continue absorbing event protocol, verification loops, and sandbox config semantics |
| [Codex](https://github.com/openai/codex) | `5c0e582c59892dbec89af78ae62c784d3da6c9cb` | Apache-2.0 | execpolicy, rule self-check samples, structured approval, JSONL events, sandbox | Currently absorbing permission-rule self-check; later structured commands and event model |
| [OpenCode](https://github.com/anomalyco/opencode) | `fab213312927ea64cf968832c527206e8c944f9e` | MIT | Provider capability layer, Agent presets, permissions, compaction, plugins and multi-client | Specialized audit exists; Provider capability matrix and system Agents stay on the later roadmap |
| [Aider](https://github.com/Aider-AI/aider) | `5dc9490bb35f9729ef2c95d00a19ccd30c26339c` | Apache-2.0 | Repo Map, architect/editor model split, post-edit lint/test | Absorb repo structure summaries and per-change-language validators; do not copy its Python implementation |
| [Cline](https://github.com/cline/cline) | `557d725690024b7c12dfad7672c476de74bd1eac` | Apache-2.0 | Shadow Git checkpoints, file/session separate restore, categorized Auto Approve | Plan MAO checkpoints; keep permission-rule priority; do not adopt model self-declared command safety |
| [Goose](https://github.com/block/goose) | `8e78960e535ab7f34630e7c5921a42f146cbc9f4` | Apache-2.0 | Recipe, extensions, automation workflows | Re-audit after Plugin API v0 stabilizes; not on the current stability-critical path |
| [Qwen Code](https://github.com/QwenLM/qwen-code) | `adf2caea3928ed46eb61e97307ad6995dd5678f2` | Apache-2.0 | Multi-model CLI, rules/extensions, headless automation | Reference for domestic-model compatibility and CLI interaction; do not reimplement existing capability |

`Roo Code` was marked archived at audit time and is not a preferred upstream for new capability.

## 2. Already Absorbed: Permission-Rule Load-Time Self-Check

Source behavior: Codex execpolicy rules can carry `justification`, `match`, and `not_match`, and examples validate rule semantics at load time. MAO independently implements the equivalent in `src/core/permission_rules.py`:

```yaml
rules:
  - action: allow
    tool: run_command
    pattern: "python -m pytest *"
    justification: "Allow project tests"
    match:
      - "python -m pytest tests"
    not_match:
      - "python -m pip install pytest"
```

- `justification` becomes a readable reason for allow or deny.
- Any expected sample in `match` that does not hit invalidates the rule.
- Any counterexample in `not_match` that incorrectly hits invalidates the rule.
- Invalid rules do not enter Agent/Worker execution boundaries and produce diagnostics with source and rule index.
- Command samples reuse MAO's compound-command splitting; path samples reuse workspace normalization and Windows case rules.

This copy was of the behavior contract only — no Codex, Grok Build, or other upstream source was copied.

Acceptance: permission-rule targeted tests `16 passed`; related Agent/Worker/Reviewer regression `53 passed`; full suite `621 passed, 1 warning`.

## 3. Next Adoption Order

### U2: Structured Commands and Verification Protocol (B4.S2 complete)

Reference Grok Build `--cwd`, tool filtering, and termination metadata, plus Codex approval events with `command: string[]`, absolute `cwd`, rationale, and optional approval decision.

- `run_command` uses structured `cwd`; do not splice workspace via `cd &&`.
- Command records include args, cwd, exit code, duration, truncation state, and permission decision.
- Permission denials carry rule rationale and safer alternatives.
- Do not copy Grok Build Unix command examples; Windows and Ubuntu both need tests.

### U3: Independent Verification Loop (folded into B4.S3–B4.S4)

Reference Grok Build `check-work` ("task list → rebuild operation trail → check current state → build tests → PASS/FAIL → at most three fix rounds"), while keeping MAO's deterministic CompletionAudit:

- Reviewer does not read Worker completion self-report; only requirements, diff, Evidence, and VerificationGate.
- After first failure, locate and fix by issue; cap at three rounds; forbid infinite self-fix token burn.
- Frontend tasks must add browser runtime and narrow-viewport smoke; TypeScript/Vite build cannot replace functional acceptance.

### U4: Stable Headless JSON/JSONL Events (folded into B4.S5)

Reference Grok Build `json/streaming-json` and Codex item started/updated/completed events:

- `mao run --output-format plain|json|streaming-json`.
- Events at least cover run, plan, model, tool, file change, command, verification, approval, compaction, usage, error, and end.
- `end` must be the last event; failures use non-zero exit code.
- Token and cost gain `usage_is_incomplete` and `cost_is_partial`; missing cost must not display as zero.
- Multi-model calls are tallied by role and real model separately; do not report only the primary model.

### U5: Task Checkpoints (after B4.S passes)

Reference Cline Shadow Git, but verify compatibility first:

- Checkpoint repo must be separate from user Git; do not write into user commit history.
- Separately support "restore files", "restore session", and "restore both".
- Track untracked files while explicitly ignoring secrets, build artifacts, and oversized files.
- Check for existing user changes before create or restore; any restore requires explicit confirm and diff preview.
- Large repos get disable, capacity caps, and cleanup policy.

MAO will never automatically run `git reset --hard` or overwrite user changes.

### U6: Repo Map and Layered Context (beta.5)

Reference Aider Repo Map symbol summaries and dependency ordering:

- Prefer language parsers/LSP/AST; fall back to file-level index when unparseable.
- Select structure by task, reference relations, recent edits, and token budget; do not stuff the whole repo into context.
- Repo Map is navigation evidence only; it cannot replace real file reads.
- With MAO multi-model fusion: recon model produces candidate structure; execution Worker gets only the slice its task needs; Reviewer gets requirement-related diff and verification evidence.

### U7: OS-Level Sandbox and Background Tasks (after beta.6)

Reference Grok Build `workspace/read-only/strict` profile, session-fixed sandbox, and fail-closed custom deny:

- Windows, Linux, and macOS each use a real, verifiable isolation backend; path-string checks must not be advertised as OS sandbox.
- When an explicitly requested custom sandbox cannot be applied, refuse to start; do not silently degrade.
- Sandbox profile is fixed with the Session; resume must not quietly enlarge permissions.
- Background commands have task id, status, incremental output, timeout, termination, and session cleanup; multi-model Workers share task ownership boundaries.

## 4. Explicitly Not Adopted

- Do not copy large Rust/TypeScript modules into a Python project (dual runtime and unmaintainable glue).
- Do not use "model declares whether a command is safe" as final permission authority.
- Do not build a plugin marketplace before signature, permission manifests, isolation, and revocation exist.
- Do not treat Shadow Git as authority to overwrite user files without confirmation.
- Do not replace evidence, tests, and browser smoke with more sub-agents.
- Do not prioritize by star count; order only by MAO real failure samples and release gates.

## 5. License Handling

MAO is currently MIT. Design ideas and public behavior contracts are independently implemented, with sources recorded here. If code is copied directly in the future:

- MIT code retains original copyright and license notices.
- Apache-2.0 code retains license, copyright, NOTICE, and prominent modification notes; related files must not be labeled MAO MIT only.
- Upstream vendored/third-party files follow their own licenses; do not judge from the repo root license alone.
- Every direct reuse must record upstream repo, commit, files, and modification scope in the commit message and third-party notices.

## 6. Current Execution Entry

B4.S1–B4.S3 and U2 are complete; U3 has multi-model frontend contracts, closure gates, and real command evidence. Historical stability slices: [`archive/completed-beta/real-task-stability-improvement-plan.md`](archive/completed-beta/real-task-stability-improvement-plan.md); current execution follows [`MAO-optimization-and-follow-up-plan.md`](MAO-optimization-and-follow-up-plan.md); U5–U7 must not jump the queue.

## 7. Primary Audit Sources

- Grok Build: [Headless](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/14-headless-mode.md), [Sandbox](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/18-sandbox.md), [Background tasks](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/20-background-tasks.md), [Permissions](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-pager/docs/user-guide/22-permissions-and-safety.md), [check-work](https://github.com/xai-org/grok-build/blob/main/crates/codegen/xai-grok-shell/skills/check-work/SKILL.md).
- Codex: [execpolicy README](https://github.com/openai/codex/blob/main/codex-rs/execpolicy/README.md), [JSONL event processor](https://github.com/openai/codex/blob/main/codex-rs/exec/src/event_processor_with_jsonl_output.rs), [approval protocol](https://github.com/openai/codex/blob/main/codex-rs/protocol/src/approvals.rs).
- Aider: [Repo Map](https://github.com/Aider-AI/aider/blob/main/aider/website/docs/repomap.md), [Architect mode](https://github.com/Aider-AI/aider/blob/main/aider/website/_posts/2024-09-26-architect.md), [linter](https://github.com/Aider-AI/aider/blob/main/aider/linter.py).
- Cline: [Checkpoints](https://github.com/cline/cline/blob/main/docs/core-workflows/checkpoints.mdx), [Auto Approve](https://github.com/cline/cline/blob/main/docs/features/auto-approve.mdx), [Permission handling](https://github.com/cline/cline/blob/main/docs/sdk/guides/permission-handling.mdx).
