"""Show that undo restores the full RuleGarden-owned transaction."""

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
    baseline = (root / "AGENTS.md").read_text(encoding="utf-8")
    task = app.begin_task("Improve parser.", [], [], [])
    rule = app.record_correction(
        task["task_id"],
        "Inspect existing code first.",
        RuleScope(),
        "User requested reuse.",
        [],
        "normal",
    )
    app.transition_rule(rule["id"], RuleStatus.STABLE)
    app.undo()
    print(json.dumps({"restored": (root / "AGENTS.md").read_text(encoding="utf-8") == baseline}))
