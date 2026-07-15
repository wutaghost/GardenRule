"""CLI contract tests for the package entry point."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_module_entrypoint_shows_help() -> None:
    """The module can be invoked before any project is initialized."""
    project_root = Path(__file__).parents[1]
    environment = os.environ | {"PYTHONPATH": str(project_root / "src")}

    result = subprocess.run(
        [sys.executable, "-m", "rulegarden.cli", "--help"],
        capture_output=True,
        check=False,
        cwd=project_root,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "Manage project-level Codex rules." in result.stdout


def test_initialize_command_creates_project_state(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[1]
    environment = os.environ | {"PYTHONPATH": str(project_root / "src")}

    result = subprocess.run(
        [sys.executable, "-m", "rulegarden.cli", "initialize", "--project-root", str(tmp_path)],
        capture_output=True,
        check=False,
        cwd=project_root,
        env=environment,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert '"initialized": true' in result.stdout
    assert (tmp_path / ".rulegarden" / "rules.yaml").is_file()
    assert (tmp_path / "AGENTS.md").is_file()


def test_cli_runs_the_explicit_rule_lifecycle(tmp_path: Path) -> None:
    project_root = Path(__file__).parents[1]
    environment = os.environ | {"PYTHONPATH": str(project_root / "src")}

    def run(*arguments: str) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, "-m", "rulegarden.cli", *arguments, "--project-root", str(tmp_path)],
            capture_output=True,
            check=False,
            cwd=project_root,
            env=environment,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        return json.loads(result.stdout)

    run("initialize")
    task = run("begin-task", "--summary", "Fix API validation.", "--task-type", "bugfix")
    task_id = str(task["task_id"])
    added = run(
        "record-correction",
        task_id,
        "Modify only relevant files.",
        "--summary",
        "User requested a narrower change.",
        "--task-type",
        "bugfix",
    )
    rule_id = str(added["id"])
    run("transition", rule_id, "stable")

    listed = run("list")
    assert listed["rules"][0]["status"] == "stable"
    assert "Modify only relevant files." in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    run("undo")
    assert "Modify only relevant files." not in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
