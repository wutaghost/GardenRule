"""Show a learned dynamic rule being loaded by a later matching task."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from rulegarden.app import RuleGardenApplication
from rulegarden.models import RuleScope


with TemporaryDirectory(prefix="rulegarden-example-") as directory:
    app = RuleGardenApplication(Path(directory))
    app.initialize()
    first_task = app.begin_task("Fix API validation.", ["bugfix"], ["src/api/users.py"], [])
    app.record_correction(
        first_task["task_id"],
        "Modify only relevant files.",
        RuleScope(task_types=["bugfix"]),
        "User requested a narrower change.",
        ["src/api/users.py"],
        "normal",
    )
    app.finish_task(first_task["task_id"])
    later_task = app.begin_task("Fix another API issue.", ["bugfix"], ["src/api/admin.py"], [])
    print(json.dumps({"selected_rule_count": len(later_task["rules"])}))
