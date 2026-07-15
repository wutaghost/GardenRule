"""Show explicit promotion of a learned rule into the AGENTS.md managed block."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rulegarden.app import RuleGardenApplication
from rulegarden.models import RuleScope, RuleStatus


with TemporaryDirectory(prefix="rulegarden-example-") as directory:
    root = Path(directory)
    app = RuleGardenApplication(root)
    app.initialize()
    task = app.begin_task("Improve a parser.", [], [], [])
    rule = app.record_correction(
        task["task_id"],
        "Inspect existing code first.",
        RuleScope(),
        "User requested reuse before new implementation.",
        [],
        "normal",
    )
    app.transition_rule(rule["id"], RuleStatus.STABLE)
    print(json.dumps({"stable_rule_in_agents": "Inspect existing code first." in (root / "AGENTS.md").read_text(encoding="utf-8")}))
