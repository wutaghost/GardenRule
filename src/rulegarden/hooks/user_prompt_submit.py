"""UserPromptSubmit Hook handler that deliberately avoids persisting the prompt."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def handle(payload: dict[str, Any], project_root: Path | None = None) -> dict[str, Any]:
    """Remind Codex of the task workflow without inspecting or echoing raw prompt text."""
    del payload, project_root
    return {
        "continue": True,
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": (
                "Before planning a coding task, call rulegarden_begin_task. "
                "When a user correction implies a durable rule, call rulegarden_record_correction."
            ),
        },
    }
