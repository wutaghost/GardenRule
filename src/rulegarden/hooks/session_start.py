"""SessionStart Hook handler."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rulegarden.hooks.common import resolve_project_root
from rulegarden.storage.repository import RuleRepository


def handle(payload: dict[str, Any], project_root: Path | None = None) -> dict[str, Any]:
    """Add concise context about initialization and any unfinished task state."""
    root = resolve_project_root(payload, project_root)
    repository = RuleRepository(root)
    if not repository.rulegarden_dir.exists():
        context = "RuleGarden is not initialized for this project. Use rulegarden_initialize before recording rules."
    else:
        active_task = repository.get_current_task_id()
        context = (
            f"RuleGarden has an unfinished task ({active_task}); finish it before ending this work."
            if active_task
            else "RuleGarden is initialized. Start coding tasks with rulegarden_begin_task."
        )
    return {
        "continue": True,
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context},
    }
