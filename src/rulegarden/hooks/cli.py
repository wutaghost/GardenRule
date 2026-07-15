"""STDIN/STDOUT command adapter required by Codex command hooks."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from rulegarden.hooks.common import fail_open
from rulegarden.hooks import post_tool_use, pre_tool_use, session_start, stop, user_prompt_submit


_HANDLERS = {
    "SessionStart": session_start.handle,
    "UserPromptSubmit": user_prompt_submit.handle,
    "PreToolUse": pre_tool_use.handle,
    "PostToolUse": post_tool_use.handle,
    "Stop": stop.handle,
}


def main(argv: list[str] | None = None) -> int:
    """Read one Hook JSON object and always emit a non-blocking JSON response."""
    parser = argparse.ArgumentParser(prog="rulegarden-hook")
    parser.add_argument("event", choices=sorted(_HANDLERS))
    args = parser.parse_args(argv)
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload must be an object")
        output: dict[str, Any] = _HANDLERS[args.event](payload)
    except Exception:
        output = fail_open(args.event)
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
