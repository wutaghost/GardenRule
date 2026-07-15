"""Filesystem contracts for the RuleGarden repository."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from rulegarden.models import EvidenceEvent, Rule, RuleDocument, TaskState


def _repository_module():
    """Load the future storage module inside tests to preserve a RED failure."""
    try:
        return importlib.import_module("rulegarden.storage.repository")
    except ModuleNotFoundError as error:
        pytest.fail(f"rulegarden.storage.repository has not been implemented: {error}")


def test_initialize_creates_empty_rules_document_and_ignores_runtime(tmp_path: Path) -> None:
    repository = _repository_module().RuleRepository(tmp_path)

    repository.initialize_storage()

    assert repository.load_rules() == RuleDocument()
    assert (tmp_path / ".rulegarden" / "rules.yaml").is_file()
    assert "runtime/" in (tmp_path / ".rulegarden" / ".gitignore").read_text(encoding="utf-8")


def test_rules_round_trip_through_yaml(tmp_path: Path) -> None:
    repository = _repository_module().RuleRepository(tmp_path)
    document = RuleDocument(rules=[Rule(id="minimal-scope", instruction="Modify only relevant files.")])

    repository.initialize_storage()
    repository.save_rules(document)

    assert repository.load_rules() == document


def test_evidence_is_appended_as_one_redacted_json_object_per_line(tmp_path: Path) -> None:
    repository = _repository_module().RuleRepository(tmp_path)
    event = EvidenceEvent(
        event_id="evt-001",
        rule_id="minimal-scope",
        type="user_correction",
        summary="User requested a smaller change.",
    )

    repository.initialize_storage()
    repository.append_evidence(event)
    repository.append_evidence(event.model_copy(update={"event_id": "evt-002"}))

    lines = (tmp_path / ".rulegarden" / "evidence.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"summary":"User requested a smaller change."' in lines[0]


def test_corrupt_rules_yaml_is_reported_without_replacing_the_file(tmp_path: Path) -> None:
    storage = _repository_module()
    repository = storage.RuleRepository(tmp_path)
    repository.initialize_storage()
    rules_path = tmp_path / ".rulegarden" / "rules.yaml"
    corrupt_contents = "rules: [unterminated"
    rules_path.write_text(corrupt_contents, encoding="utf-8")

    with pytest.raises(storage.StorageError):
        repository.load_rules()

    assert rules_path.read_text(encoding="utf-8") == corrupt_contents


def test_failed_atomic_replace_preserves_the_previous_rules_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _repository_module()
    repository = storage.RuleRepository(tmp_path)
    original = RuleDocument(rules=[Rule(id="minimal-scope", instruction="Modify only relevant files.")])
    replacement = RuleDocument(rules=[Rule(id="reuse-code", instruction="Inspect existing code first.")])
    repository.initialize_storage()
    repository.save_rules(original)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("simulated interrupted replacement")

    monkeypatch.setattr(storage.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated interrupted replacement"):
        repository.save_rules(replacement)

    assert repository.load_rules() == original


def test_runtime_task_state_can_be_removed_after_task_completion(tmp_path: Path) -> None:
    repository = _repository_module().RuleRepository(tmp_path)
    state = TaskState(task_id="task-001", task_summary="Add a rule.")
    repository.initialize_storage()

    repository.save_task_state(state)
    assert repository.load_task_state("task-001") == state

    repository.delete_task_state("task-001")
    assert repository.load_task_state("task-001") is None
