"""Codex Hook behavior tests using the same project state as MCP workflows."""

from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

from rulegarden.app import RuleGardenApplication


def _hooks_module(name: str):
    """Load a future hook module inside tests so missing implementation stays RED."""
    try:
        return importlib.import_module(f"rulegarden.hooks.{name}")
    except ModuleNotFoundError as error:
        pytest.fail(f"RuleGarden hook '{name}' has not been implemented: {error}")


def test_user_prompt_hook_returns_context_without_echoing_the_prompt(tmp_path: Path) -> None:
    hook = _hooks_module("user_prompt_submit")
    app = RuleGardenApplication(tmp_path)
    app.initialize()
    raw_prompt = "Do not persist: SECRET-EXAMPLE-123"

    output = hook.handle({"cwd": str(tmp_path), "user_prompt": raw_prompt}, tmp_path)

    serialized = json.dumps(output)
    assert "rulegarden_begin_task" in serialized
    assert raw_prompt not in serialized


def test_pre_tool_hook_warns_on_destructive_git_command_without_claiming_to_block(tmp_path: Path) -> None:
    hook = _hooks_module("pre_tool_use")

    output = hook.handle(
        {"cwd": str(tmp_path), "tool_name": "Bash", "tool_input": {"command": "git reset --hard"}},
        tmp_path,
    )

    assert "ADVISORY" in output["systemMessage"]
    assert "git reset --hard" in output["systemMessage"]
    assert "continue" not in output


def test_post_tool_hook_records_paths_for_the_current_task(tmp_path: Path) -> None:
    hook = _hooks_module("post_tool_use")
    app = RuleGardenApplication(tmp_path)
    app.initialize()
    task = app.begin_task("Change the API.", [], [], [])

    hook.handle(
        {
            "cwd": str(tmp_path),
            "tool_name": "apply_patch",
            "tool_input": {"file_path": "src/api/users.py"},
        },
        tmp_path,
    )

    state = app.repository.load_task_state(task["task_id"])
    assert state is not None
    assert state.touched_paths == ["src/api/users.py"]


def test_stop_hook_requests_one_finish_pass_then_avoids_recursion(tmp_path: Path) -> None:
    hook = _hooks_module("stop")
    app = RuleGardenApplication(tmp_path)
    app.initialize()
    app.begin_task("Change the API.", [], [], [])

    first = hook.handle({"cwd": str(tmp_path)}, tmp_path)
    second = hook.handle({"cwd": str(tmp_path)}, tmp_path)

    assert first["continue"] is False
    assert "rulegarden_finish_task" in first["systemMessage"]
    assert second["continue"] is True


def test_hook_cli_fails_open_for_malformed_input(tmp_path: Path) -> None:
    source_root = Path(__file__).parents[2] / "src"
    environment = {"PYTHONPATH": str(source_root)}

    result = subprocess.run(
        [sys.executable, "-m", "rulegarden.hooks.cli", "UserPromptSubmit"],
        input="{bad json",
        capture_output=True,
        check=False,
        cwd=tmp_path,
        env=environment,
        text=True,
    )

    assert result.returncode == 0
    assert json.loads(result.stdout)["continue"] is True
    assert not (tmp_path / ".rulegarden").exists()
