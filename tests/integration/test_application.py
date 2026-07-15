"""Application-service workflow tests without transport-specific mocks."""

from __future__ import annotations

import importlib
import subprocess
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


def test_transition_to_dynamic_reactivates_a_disabled_rule_at_the_requested_status(tmp_path: Path) -> None:
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
    app.transition_rule(added["id"], RuleStatus.DISABLED)

    reactivated = app.transition_rule(added["id"], RuleStatus.DYNAMIC)

    assert reactivated["status"] == "dynamic"


def test_finish_task_commits_only_rulegarden_changes_when_the_project_is_ready(tmp_path: Path) -> None:
    app_module = _application_module()
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "RuleGarden Tests"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "tests@example.invalid"], cwd=tmp_path, check=True)
    app = app_module.RuleGardenApplication(tmp_path)
    app.initialize()
    subprocess.run(["git", "add", "AGENTS.md", ".rulegarden/rules.yaml"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "baseline"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("unrelated user work\n", encoding="utf-8")

    task = app.begin_task("Add a stable rule.", [], [], [])
    added = app.record_correction(
        task["task_id"],
        "Inspect existing code first.",
        RuleScope(),
        "User requested reuse.",
        [],
        "normal",
    )
    app.transition_rule(added["id"], RuleStatus.STABLE)

    summary = app.finish_task(task["task_id"])

    assert summary["commit"]["status"] == "committed"
    changed_paths = subprocess.run(
        ["git", "show", "--pretty=", "--name-only", "HEAD"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert changed_paths == [".rulegarden/rules.yaml", "AGENTS.md"]
    assert "README.md" in subprocess.run(
        ["git", "status", "--short"], cwd=tmp_path, check=True, capture_output=True, text=True
    ).stdout
