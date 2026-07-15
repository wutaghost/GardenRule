# RuleGarden

RuleGarden turns repeated coding-agent corrections into structured, project-level rules. Rules begin as task-aware dynamic guidance, become stable only through explicit promotion, and can be reversed as complete transactions.

The first release targets one developer using Codex with a project `AGENTS.md` file. It stores rules and redacted evidence under `.rulegarden/`; it does not retain full user prompts after a task finishes.

## What It Does

- Initializes a non-destructive RuleGarden block inside `AGENTS.md`.
- Stores rules in `.rulegarden/rules.yaml` with validated lifecycle state.
- Returns only relevant dynamic and stable rules for a task's paths and types.
- Records concise correction evidence without prompts, transcripts, tokens, or secrets.
- Promotes, demotes, disables, deletes, and undoes rules through reversible transactions.
- Creates a rules-only Git commit at task completion when it can prove user changes are excluded.
- Provides a local STDIO MCP server, CLI, Codex Skill, and advisory lifecycle Hooks.

## Limits

Current Codex `PreToolUse` Hooks can add a warning but cannot reliably reject a tool call. RuleGarden therefore treats high-risk commands such as `git reset --hard` as advisory warnings, not hard security enforcement. Use repository protections and Codex permission controls for mandatory safeguards.

Automatic promotion and demotion are intentionally deferred. The MVP records the metrics needed for those decisions, while promotion remains explicit so unvalidated thresholds cannot pollute long-lived project guidance.

## Install For Development

Requires Python 3.11 or later and Git for transaction commits.

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m pytest -q
```

This installs three commands:

```text
rulegarden
rulegarden-mcp
rulegarden-hook
```

## Use The CLI

```powershell
rulegarden initialize --project-root E:\my-project
rulegarden begin-task --summary "Fix API validation" --task-type bugfix --project-root E:\my-project
rulegarden list --project-root E:\my-project
rulegarden undo --project-root E:\my-project
```

`record-correction` needs the task ID returned by `begin-task`:

```powershell
rulegarden record-correction <task-id> "Modify only relevant files." `
  --summary "User requested a narrower change." `
  --task-type bugfix `
  --project-root E:\my-project
```

Use `rulegarden transition <rule-id> stable` to compile a stable rule into the managed `AGENTS.md` block. Use `dynamic`, `disabled`, or `deleted` for explicit lifecycle changes.

## Use With Codex

The installable plugin bundle is in [`plugins/rulegarden`](plugins/rulegarden). It supplies:

- `.mcp.json`, which launches `rulegarden-mcp`.
- `hooks/hooks.json`, which runs `rulegarden-hook` for supported lifecycle events.
- `skills/rulegarden/SKILL.md`, which tells Codex when to use the MCP tools.

Install the Python package before enabling the plugin. Review and trust Hook definitions in Codex before they run. The plugin is deliberately kept as a repository artifact; no personal Marketplace entry is created during development.

The plugin Skill passes `project_root` to each MCP tool. This matters because a plugin's own cache directory is not the repository whose rules should be managed.

For a direct local MCP connection, configure an STDIO server that runs `rulegarden-mcp`. Every tool accepts an optional `project_root`; provide the current repository root when the server is not launched from that root.

## Project Data

```text
my-project/
  AGENTS.md
  .rulegarden/
    rules.yaml       # source of truth
    evidence.jsonl   # redacted summaries only
    history.jsonl    # reversible rule transactions
    state.json       # current task ID only
    runtime/         # ephemeral task summaries, ignored by Git
```

RuleGarden changes only the content between these markers:

```markdown
<!-- RULEGARDEN:START -->
## RuleGarden Stable Rules
<!-- RULEGARDEN:END -->
```

If those markers are malformed or duplicated, RuleGarden refuses to guess and reports an error instead of rewriting `AGENTS.md`.

## Git Behavior

When a task changed RuleGarden state, `finish-task` attempts a commit containing only:

- `.rulegarden/rules.yaml`
- `.rulegarden/config.yaml` when present
- the RuleGarden-managed `AGENTS.md` block

It uses a temporary Git index. User business code, user documentation edits, runtime files, and other untracked work are not staged. If `AGENTS.md` is untracked, RuleGarden paths are already staged, or the target is not a Git repository, it skips the commit and returns the reason.

## Examples

The executable examples use temporary projects and print JSON:

```powershell
$env:PYTHONPATH = "src"
py examples\repeated-correction\run.py
py examples\rule-promotion\run.py
py examples\high-risk-warning\run.py
py examples\rule-demotion\run.py
py examples\undo-transaction\run.py
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
