"""Shared payload and failure handling for RuleGarden command hooks."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def resolve_project_root(payload: dict[str, Any], project_root: Path | None = None) -> Path:
    """Prefer an explicit test/config root, then the Hook's own working directory."""
    if project_root is not None:
        return Path(project_root)
    cwd = payload.get("cwd")
    return Path(cwd) if isinstance(cwd, str) and cwd else Path.cwd()


def fail_open(event_name: str) -> dict[str, Any]:
    """Return a valid, non-blocking response without leaking malformed Hook input."""
    if event_name == "PreToolUse":
        return {"systemMessage": "RuleGarden advisory hook skipped because its input was invalid."}
    return {"continue": True, "systemMessage": "RuleGarden hook skipped because its input was invalid."}
