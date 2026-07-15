"""CLI contract tests for the package entry point."""

from __future__ import annotations

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
