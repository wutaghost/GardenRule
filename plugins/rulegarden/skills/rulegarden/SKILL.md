---
name: rulegarden
description: Manage project-level coding-agent rules with the RuleGarden MCP tools. Use when the user asks to initialize RuleGarden, remember a correction, list or change project rules, or undo a RuleGarden rule transaction.
---

Determine the current repository root before every MCP call and pass it as `project_root`.

1. At the beginning of a coding task, call `rulegarden_begin_task` with the task summary, task types, expected paths, risk signals, and `project_root`.
2. When the user corrects agent behavior or explicitly asks to remember a requirement, call `rulegarden_record_correction`. Store a concise evidence summary only; never supply the full user prompt.
3. Before ending a task that has RuleGarden activity, call `rulegarden_finish_task` with the task ID and `project_root`.
4. Use `rulegarden_transition_rule` for explicit promotion, demotion, disablement, or deletion. Use `rulegarden_undo` to reverse a complete RuleGarden transaction.
5. Treat high-risk PreToolUse responses as advisory warnings. Do not claim that a Hook blocked an operation.
