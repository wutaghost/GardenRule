"""Tests for commits that must exclude user-owned worktree changes."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

from rulegarden.agents_md.managed_block import render_stable_block
from rulegarden.models import Rule, RuleStatus


def _git_module():
    """Load the future commit manager inside tests for a clear RED failure."""
    try:
        return importlib.import_module("rulegarden.git.isolated_commit")
    except ModuleNotFoundError as error:
        pytest.fail(f"isolated Git commit manager has not been implemented: {error}")


def _run(project_root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=project_root, check=True, capture_output=True, text=True)
    return result.stdout


def _initialize_repository(project_root: Path) -> None:
    _run(project_root, "init", "-q")
    _run(project_root, "config", "user.name", "RuleGarden Tests")
    _run(project_root, "config", "user.email", "tests@example.invalid")
    agents = "# Project\n\n" + render_stable_block([]) + "\n\nUser-owned footer.\n"
    (project_root / "AGENTS.md").write_text(agents, encoding="utf-8")
    (project_root / ".rulegarden").mkdir()
    (project_root / ".rulegarden" / "rules.yaml").write_text("version: 1\nrules: []\n", encoding="utf-8")
    (project_root / "README.md").write_text("baseline\n", encoding="utf-8")
    _run(project_root, "add", "AGENTS.md", ".rulegarden/rules.yaml", "README.md")
    _run(project_root, "commit", "-qm", "baseline")


def test_commit_uses_only_rulegarden_paths_when_worktree_is_dirty(tmp_path: Path) -> None:
    git = _git_module()
    _initialize_repository(tmp_path)
    stable = Rule(id="minimal-scope", instruction="Modify only relevant files.", status=RuleStatus.STABLE)
    (tmp_path / "AGENTS.md").write_text(
        "# Project\n\n" + render_stable_block([stable]) + "\n\nUser-owned footer.\n",
        encoding="utf-8",
    )
    (tmp_path / ".rulegarden" / "rules.yaml").write_text("version: 1\nrules:\n- id: minimal-scope\n", encoding="utf-8")
    (tmp_path / "README.md").write_text("user edit\n", encoding="utf-8")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "business.py").write_text("user code\n", encoding="utf-8")
    (tmp_path / ".rulegarden" / "runtime").mkdir()
    (tmp_path / ".rulegarden" / "runtime" / "task.json").write_text("temporary\n", encoding="utf-8")

    result = git.IsolatedCommitManager(tmp_path).commit_rulegarden_changes("chore(rulegarden): update rules")

    assert result.status == "committed"
    committed_paths = _run(tmp_path, "show", "--pretty=", "--name-only", "HEAD").splitlines()
    assert committed_paths == [".rulegarden/rules.yaml", "AGENTS.md"]
    status = _run(tmp_path, "status", "--short")
    assert "README.md" in status
    assert "src/" in status.replace("\\", "/")
    assert "runtime" in status


def test_untracked_agents_file_causes_a_safe_commit_skip(tmp_path: Path) -> None:
    git = _git_module()
    _run(tmp_path, "init", "-q")
    _run(tmp_path, "config", "user.name", "RuleGarden Tests")
    _run(tmp_path, "config", "user.email", "tests@example.invalid")
    (tmp_path / "README.md").write_text("baseline\n", encoding="utf-8")
    _run(tmp_path, "add", "README.md")
    _run(tmp_path, "commit", "-qm", "baseline")
    (tmp_path / "AGENTS.md").write_text(render_stable_block([]), encoding="utf-8")
    (tmp_path / ".rulegarden").mkdir()
    (tmp_path / ".rulegarden" / "rules.yaml").write_text("version: 1\nrules: []\n", encoding="utf-8")

    result = git.IsolatedCommitManager(tmp_path).commit_rulegarden_changes("chore(rulegarden): update rules")

    assert result.status == "skipped"
    assert result.reason == "agents_md_is_untracked"


def test_non_git_directory_skips_without_creating_any_files(tmp_path: Path) -> None:
    git = _git_module()

    result = git.IsolatedCommitManager(tmp_path).commit_rulegarden_changes("chore(rulegarden): update rules")

    assert result.status == "skipped"
    assert result.reason == "not_a_git_repository"
    assert not (tmp_path / ".git").exists()
