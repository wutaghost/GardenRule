"""Stop Hook handler that requests one task-finalization pass."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rulegarden.hooks.common import resolve_project_root
from rulegarden.storage.repository import RuleRepository


def handle(payload: dict[str, Any], project_root: Path | None = None) -> dict[str, Any]:
    """Request finish_task once, then allow the following Stop event to complete normally."""
    repository = RuleRepository(resolve_project_root(payload, project_root))
    task_id = repository.get_current_task_id()
    if task_id is None or repository.load_task_state(task_id) is None:
        return {"continue": True}
    if not repository.mark_stop_notified(task_id):
        return {"continue": True}
    return {
        "continue": False,
        "stopReason": "RuleGarden task is still open.",
        "systemMessage": f"Call rulegarden_finish_task for task '{task_id}' before ending this response.",
    }
