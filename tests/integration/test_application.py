"""Application-service workflow tests without transport-specific mocks."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from rulegarden.models import RuleScope, RuleStatus


def _application_module():
    """Load the future application module inside tests for a clear RED failure."""
    try:
        return importlib.import_module("rulegarden.app")
    except ModuleNotFoundError as error:
        pytest.fail(f"application service has not been implemented: {error}")


def test_correction_becomes_a_dynamic_rule_and_is_removed_from_runtime_on_finish(tmp_path: Path) -> None:
    app_module = _application_module()
    app = app_module.RuleGardenApplication(tmp_path)
    app.initialize()
    task = app.begin_task(
        task_summary="Fix API validation.",
        task_types=["bugfix"],
        expected_paths=["src/api/users.py"],
        risk_signals=[],
    )

    recorded = app.record_correction(
        task_id=task["task_id"],
        candidate_instruction="Modify only relevant files.",
        scope=RuleScope(task_types=["bugfix"]),
        evidence_summary="User requested a narrower change.",
        affected_paths=["src/api/users.py"],
        severity="normal",
    )
    next_task = app.begin_task(
        task_summary="Fix another API validation issue.",
        task_types=["bugfix"],
        expected_paths=["src/api/admin.py"],
        risk_signals=[],
    )

    assert recorded["status"] == "dynamic"
    assert [rule["instruction"] for rule in next_task["rules"]] == ["Modify only relevant files."]
    assert "evidence" not in next_task["rules"][0]

    app.finish_task(task["task_id"])

    assert app.repository.load_task_state(task["task_id"]) is None
    evidence = (tmp_path / ".rulegarden" / "evidence.jsonl").read_text(encoding="utf-8")
    assert "User requested a narrower change." in evidence
    assert "Fix API validation." not in evidence


def test_transition_compiles_stable_rule_and_undo_reverts_it(tmp_path: Path) -> None:
    app_module = _application_module()
    app = app_module.RuleGardenApplication(tmp_path)
    app.initialize()
    task = app.begin_task("Add a rule.", [], [], [])
    added = app.record_correction(
        task["task_id"],
        "Inspect existing code first.",
        RuleScope(),
        "User requested reuse.",
        [],
        "normal",
    )

    app.transition_rule(added["id"], RuleStatus.STABLE)

    assert "Inspect existing code first." in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    app.undo()

    assert "Inspect existing code first." not in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
