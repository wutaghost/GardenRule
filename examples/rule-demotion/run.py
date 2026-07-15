"""Show a stable rule returning to dynamic state through an explicit transition."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rulegarden.app import RuleGardenApplication
from rulegarden.models import RuleScope, RuleStatus


with TemporaryDirectory(prefix="rulegarden-example-") as directory:
    app = RuleGardenApplication(Path(directory))
    app.initialize()
    task = app.begin_task("Refactor parser.", [], [], [])
    rule = app.record_correction(
        task["task_id"],
        "Reuse parser helpers.",
        RuleScope(),
        "User requested existing helper reuse.",
        [],
        "normal",
    )
    app.transition_rule(rule["id"], RuleStatus.STABLE)
    demoted = app.transition_rule(rule["id"], RuleStatus.DYNAMIC)
    print(json.dumps({"status": demoted["status"]}))
