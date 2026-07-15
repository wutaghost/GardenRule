"""Show that destructive commands receive an advisory warning, not a claimed hard block."""

from __future__ import annotations

import json

from rulegarden.hooks.pre_tool_use import handle


print(json.dumps(handle({"tool_name": "Bash", "tool_input": {"command": "git reset --hard"}})))
