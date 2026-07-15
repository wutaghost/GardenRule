# RuleGarden MVP Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Deliver a local, project-scoped RuleGarden that persists project rules, compiles stable rules into an isolated `AGENTS.md` block, returns task-relevant rules through MCP, and records reversible rule transactions without retaining full prompts.

**Architecture:** Build the core as a Python package and CLI first. A local STDIO MCP server invokes the same application services as the CLI; Codex hooks only create ephemeral task state, add advisory context, and collect observable tool activity. The plugin is packaging work after the workflow is proven in a project configuration.

**Tech Stack:** Python 3.11+, MCP Python SDK, Pydantic v2, PyYAML, pytest, Git CLI, `uv` or `pip` for environment management.

---

## Scope and feasibility decisions

The first build intentionally differs from the proposal in four places:

- `block` means an advisory high-severity warning. Current documented Codex `PreToolUse` hooks cannot reject a tool call; they support `systemMessage` only. Do not label this behaviour as enforcement.
- Rule acquisition is explicit command input or a Codex MCP call made after the model identifies a correction. Hooks must not infer semantic corrections from raw prompts.
- Stable promotion is explicit (`/rulegarden promote <id>`) in the MVP. Collect metrics now; enable automatic promotion only after real data defines thresholds.
- Automatic Git commits are implemented only when RuleGarden can construct a patch containing no user-owned content. Otherwise retain the transaction and report `commit_skipped_dirty_scope`.

**Out of scope:** a web UI, a visual garden, non-Codex hosts, cloud sync, team workflows, automatic semantic merge by another LLM, reliable hard operation blocking, and automatic promotion/demotion decisions.

## User-visible workflow

1. `rulegarden initialize` creates `.rulegarden/`, imports the existing `AGENTS.md` as untouched content, and inserts a marked empty managed block.
2. At task start Codex calls `rulegarden_begin_task` with explicit tags and expected paths; the server returns matching dynamic and stable rules.
3. Codex records a correction through `rulegarden_record_correction`, or the user invokes `/rulegarden add ...` through the skill/CLI command.
4. At task finish Codex calls `rulegarden_finish_task`; the server writes evidence summaries, expires the runtime prompt copy, updates counters, and creates one reversible transaction.
5. `rulegarden promote`, `disable`, `enable`, `delete`, and `undo` are deterministic state transitions. Promotion updates only the managed AGENTS block.

## Repository layout

```text
rulegarden/
  pyproject.toml
  README.md
  src/rulegarden/
    cli.py
    app.py
    models.py
    errors.py
    storage/repository.py
    storage/runtime.py
    rules/selector.py
    rules/lifecycle.py
    agents_md/managed_block.py
    transactions/service.py
    git/isolated_commit.py
    mcp/server.py
    hooks/common.py
    hooks/session_start.py
    hooks/user_prompt_submit.py
    hooks/pre_tool_use.py
    hooks/post_tool_use.py
    hooks/stop.py
  plugin/
    .codex-plugin/plugin.json
    hooks/hooks.json
    skills/rulegarden/SKILL.md
  tests/unit/
  tests/integration/
  tests/fixtures/
```

The installed project data remains separate from the package:

```text
target-project/
  AGENTS.md
  .codex/hooks.json
  .rulegarden/
    rules.yaml
    evidence.jsonl
    history.jsonl
    state.json
    config.yaml
    runtime/             # ignored; no prompt survives finish or failure cleanup
    transactions/
```

## Data and interface contracts

`rules.yaml` is the source of truth. Validate it with Pydantic before every write. The minimal rule fields are `id`, `instruction`, `status`, `enabled`, `source_type`, `enforcement`, `risk_level`, `scope`, `evidence`, `metrics`, and timestamps. `scope` supports `paths` and `task_types`; selection is an OR within each populated field and an AND across populated field types.

`history.jsonl` is append-only transaction metadata. Each transaction stores the previous and next serialized rule set, the old and new managed AGENTS block, changed rule IDs, and a commit outcome. `evidence.jsonl` stores only the supplied summary, paths, event type, task ID, and timestamp. It must reject keys named `prompt`, `transcript`, `secret`, `token`, or `api_key`.

MCP tools for MVP:

| Tool | Input | Deterministic result |
| --- | --- | --- |
| `rulegarden_initialize` | project root | initialized state and backup transaction |
| `rulegarden_begin_task` | summary, tags, paths, risk signals | task id and matching rules |
| `rulegarden_record_correction` | task id, instruction, scope, summary | dynamic rule and evidence event |
| `rulegarden_finish_task` | task id | transaction id and concise change summary |
| `rulegarden_list_rules` | optional status | rule summaries only |
| `rulegarden_transition_rule` | id, target status | validated transition result |
| `rulegarden_undo` | optional transaction id | restored transaction result |

The MCP initialization instruction must be shorter than 512 characters and require only `begin_task`, `record_correction` when a correction is identified, and `finish_task` when a rule event exists.

## Development plan

### Task 1: Create the package and test harness

**Files:** Create `pyproject.toml`, `src/rulegarden/__init__.py`, `tests/conftest.py`, `.gitignore`, `README.md`.

1. Run `git init` in the implementation repository and create a Python 3.11 virtual environment.
2. Add runtime dependencies: `mcp`, `pydantic`, and `pyyaml`; add `pytest` as the test dependency.
3. Write a smoke test importing `rulegarden` and invoking `rulegarden --help`.
4. Run `pytest -q`; expected result: the smoke test passes.
5. Commit `chore: bootstrap rulegarden package`.

### Task 2: Define validated state models

**Files:** Create `src/rulegarden/models.py`, `src/rulegarden/errors.py`, `tests/unit/test_models.py`.

1. Write failing tests for invalid status, invalid enforcement, absent instruction, duplicate IDs, and forbidden evidence fields.
2. Implement Pydantic models: `Rule`, `RuleScope`, `RuleMetrics`, `EvidenceEvent`, `TaskState`, and `Transaction`.
3. Add concise comments to explain the privacy redaction boundary and valid lifecycle transitions.
4. Run `pytest tests/unit/test_models.py -q`; expected result: all model validation tests pass.
5. Commit `feat: add validated rule models`.

### Task 3: Implement atomic repository storage

**Files:** Create `src/rulegarden/storage/repository.py`, `src/rulegarden/storage/runtime.py`, `tests/unit/test_repository.py`.

1. Write failing tests for creating an empty state, round-tripping YAML, append-only JSONL evidence, corrupt YAML rejection, and atomic-write recovery.
2. Implement temp-file write followed by `os.replace`; never truncate the current state before validation succeeds.
3. Write runtime task files under `.rulegarden/runtime/<task-id>.json` with restrictive ownership where supported; delete them in a `finally` path in `finish_task`.
4. Run the storage tests and add a test asserting the runtime directory is ignored by generated `.gitignore`.
5. Commit `feat: persist rulegarden state atomically`.

### Task 4: Make AGENTS.md editing narrow and reversible

**Files:** Create `src/rulegarden/agents_md/managed_block.py`, `tests/unit/test_managed_block.py`, `tests/fixtures/agents_with_user_content.md`.

1. Write failing tests for insertion, replacement, malformed duplicate markers, unchanged user content, no-op compilation, and undo restoration.
2. Implement marker constants `<!-- RULEGARDEN:START -->` and `<!-- RULEGARDEN:END -->`; parse the whole file but mutate only the byte span between markers.
3. Compile only enabled `stable` rules, ordered by `risk_level`, then creation time, under a configurable byte budget. On overflow, fail with a diagnostic; do not silently drop a rule.
4. Run the unit tests and inspect a fixture diff to confirm content outside the markers is identical.
5. Commit `feat: compile stable rules into managed agents block`.

### Task 5: Add deterministic rule selection and lifecycle transitions

**Files:** Create `src/rulegarden/rules/selector.py`, `src/rulegarden/rules/lifecycle.py`, `tests/unit/test_selector.py`, `tests/unit/test_lifecycle.py`.

1. Write failing tests for path normalization on Windows, task-type matching, disabled/deleted exclusion, stable/dynamic inclusion, and invalid transitions.
2. Implement `begin_task`, manual add, promote, disable, enable, delete, and low-effect marking. New learned rules always start as `dynamic`.
3. Increment `hit_count` only when a rule is selected for a task, not when it merely exists.
4. Run focused tests, then the entire unit suite.
5. Commit `feat: add rule selection and lifecycle operations`.

### Task 6: Build transactions and safe undo

**Files:** Create `src/rulegarden/transactions/service.py`, `tests/integration/test_transactions.py`.

1. Write a failing integration test: add a rule, promote it, update AGENTS, invoke undo, then assert rule state and managed block exactly equal the baseline.
2. Implement a transaction wrapper that snapshots validated before/after state and AGENTS managed-block text before any visible write.
3. On partial failure, restore all already-written RuleGarden files. Preserve external user edits outside the managed block and report an explicit conflict if the managed block changed concurrently.
4. Run the test against a temporary Git repository.
5. Commit `feat: add reversible rule transactions`.

### Task 7: Expose CLI and MCP through one application service

**Files:** Create `src/rulegarden/app.py`, `src/rulegarden/cli.py`, `src/rulegarden/mcp/server.py`, `tests/integration/test_mcp_workflow.py`.

1. Write a failing workflow test covering initialize, begin task, record correction, finish task, list rules, promote, and undo.
2. Implement application methods once and make both Typer/argparse CLI handlers and MCP tool handlers call them. Do not duplicate validation in transport layers.
3. Return to MCP only instruction, exceptions, risk, and status. Do not expose evidence or raw runtime data through task selection.
4. Start the server using the documented STDIO transport and run the integration test through an MCP client fixture.
5. Commit `feat: expose rule lifecycle through cli and mcp`.

### Task 8: Add advisory Codex hooks

**Files:** Create `src/rulegarden/hooks/*.py`, `.codex/hooks.json` fixture, `plugin/hooks/hooks.json`, `tests/integration/test_hooks.py`.

1. Write failing tests using captured Hook JSON for SessionStart, UserPromptSubmit, PreToolUse, PostToolUse, and Stop.
2. SessionStart validates files and reports unfinished transactions; UserPromptSubmit creates transient turn state and supplies brief developer context; PreToolUse emits high-risk warnings only; PostToolUse records changed paths and operation categories; Stop reports an unclosed rule task.
3. Enforce a 5-second timeout and fail open: malformed input or internal Hook errors must never modify the repository or stop user work.
4. Test that each Hook emits valid JSON and that no Hook output contains a full prompt or file content.
5. Commit `feat: add advisory lifecycle hooks`.

### Task 9: Implement isolated Git commits with conservative fallback

**Files:** Create `src/rulegarden/git/isolated_commit.py`, `tests/integration/test_isolated_commit.py`.

1. Write a failing test with unrelated unstaged code and documentation changes, then create a rule transaction.
2. Build a temporary Git index from `HEAD`; stage only the generated `.rulegarden` tracked files and the managed-block-only AGENTS patch derived from the baseline blob.
3. Before committing, assert `git diff --cached --name-only` is a subset of the allowed files and inspect the cached AGENTS diff for lines outside the markers. If either check fails, skip the commit and retain the transaction.
4. Test clean, dirty, untracked-AGENTS, and non-Git repository outcomes.
5. Commit `feat: commit only rulegarden transaction changes`.

### Task 10: Package, document, and validate the reference scenarios

**Files:** Create `plugin/.codex-plugin/plugin.json`, `plugin/.mcp.json`, `plugin/skills/rulegarden/SKILL.md`, `examples/`, update `README.md`.

1. Keep the plugin manifest limited to the skill, MCP configuration, and advisory hooks; do not introduce a UI.
2. Document installation via a local plugin marketplace and direct project `.codex/config.toml` configuration. State that Hook definitions require review/trust.
3. Add executable examples for: repeated correction recorded as dynamic, manual promotion, high-risk warning, managed-block preservation, dirty worktree commit skip, and full undo.
4. Run `pytest -q`, package metadata validation, and every example in a disposable Git repository.
5. Commit `docs: publish rulegarden mvp setup and scenarios`.

## Acceptance tests

- Initializing a Git repository with user-owned AGENTS content changes only the marked RuleGarden block.
- A recorded correction leaves no full prompt data after `finish_task`, including exceptional paths.
- Matching selection returns only enabled rules relevant to supplied tags or paths.
- Promotion updates `rules.yaml` and the managed block in one undoable transaction.
- Disable, enable, delete, and undo retain a coherent history and never alter external files.
- Hooks provide advisory output for supported events, do not claim to block operations, and fail open.
- A clean worktree produces a rules-only Git commit; any inability to prove that property skips the commit.
- All reference scenarios run on Windows, because the initial target environment is Windows PowerShell.

## Delivery sequence and estimate

| Day | Deliverable | Exit condition |
| --- | --- | --- |
| 1 | Tasks 1-2 | Package and schema tests pass |
| 2 | Tasks 3-4 | Atomic storage and AGENTS preservation pass |
| 3 | Task 5 | Rule matching and manual lifecycle pass |
| 4 | Task 6 | Transaction/undo integration passes |
| 5-6 | Task 7 | MCP end-to-end workflow passes |
| 7 | Task 8 | Hook fixtures and privacy checks pass |
| 8-9 | Task 9 | Isolated-commit adversarial tests pass |
| 10 | Task 10 | Plugin installation and scenario suite pass |
| 11-12 | Hardening | Manual tests in Codex CLI/Desktop, defect fixes, release checklist |

## Deferred design validation

Before implementing automatic promotion or demotion, collect at least 30 completed rule events across multiple task types. Then define thresholds from observed correction recurrence, undo rate, and false-warning reports. Until then, automated lifecycle decisions would encode unvalidated assumptions rather than evidence.
