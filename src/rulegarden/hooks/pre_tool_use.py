"""Advisory PreToolUse Hook handler for known destructive commands."""

from __future__ import annotations

from pathlib import Path
from typing import Any


_HIGH_RISK_COMMANDS = (
    "git reset --hard",
    "git clean -fd",
    "rm -rf",
    "remove-item -recurse -force",
)


def handle(payload: dict[str, Any], project_root: Path | None = None) -> dict[str, Any]:
    """Warn about supported high-risk command patterns without claiming to block them."""
    del project_root
    tool_input = payload.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    normalized = command.casefold() if isinstance(command, str) else ""
    for pattern in _HIGH_RISK_COMMANDS:
        if pattern in normalized:
            return {
                "systemMessage": (
                    f"RULEGARDEN ADVISORY: this command matches '{pattern}'. "
                    "Inspect the working tree and use a reversible alternative when possible."
                )
            }
    return {}
