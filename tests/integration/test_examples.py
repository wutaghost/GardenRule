"""Reference examples must remain executable against the packaged workflow."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


EXAMPLES_ROOT = Path(__file__).parents[2] / "examples"
SOURCE_ROOT = Path(__file__).parents[2] / "src"


def _run_example(name: str) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, str(EXAMPLES_ROOT / name / "run.py")],
        capture_output=True,
        check=False,
        env=os.environ | {"PYTHONPATH": str(SOURCE_ROOT)},
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_reference_examples_cover_the_documented_workflows() -> None:
    repeated = _run_example("repeated-correction")
    promotion = _run_example("rule-promotion")
    warning = _run_example("high-risk-warning")
    demotion = _run_example("rule-demotion")
    undo = _run_example("undo-transaction")

    assert repeated["selected_rule_count"] == 1
    assert promotion["stable_rule_in_agents"] is True
    assert "ADVISORY" in warning["systemMessage"]
    assert demotion["status"] == "dynamic"
    assert undo["restored"] is True
