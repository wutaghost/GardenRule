"""PostToolUse Hook handler that records modified paths for the current task."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rulegarden.hooks.common import resolve_project_root
from rulegarden.storage.repository import RuleRepository


def handle(payload: dict[str, Any], project_root: Path | None = None) -> dict[str, Any]:
    """Add paths from supported tool payload fields to ephemeral task state only."""
    repository = RuleRepository(resolve_project_root(payload, project_root))
    task_id = repository.get_current_task_id()
    if task_id is None:
        return {}
    task = repository.load_task_state(task_id)
    if task is None:
        repository.clear_current_task(task_id)
        return {}
    paths = _extract_paths(payload.get("tool_input"))
    if not paths:
        return {}
    touched_paths = [*task.touched_paths]
    for path in paths:
        if path not in touched_paths:
            touched_paths.append(path)
    repository.save_task_state(task.model_copy(update={"touched_paths": touched_paths}))
    return {"systemMessage": f"RuleGarden recorded {len(paths)} modified path(s) for the active task."}


def _extract_paths(tool_input: Any) -> list[str]:
    """Read only explicit path fields; never parse file contents or command output as paths."""
    if not isinstance(tool_input, dict):
        return []
    paths: list[str] = []
    for key in ("file_path", "path", "file"):
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            paths.append(value)
    values = tool_input.get("paths")
    if isinstance(values, list):
        paths.extend(value for value in values if isinstance(value, str) and value)
    return paths
