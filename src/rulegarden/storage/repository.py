"""Atomic filesystem storage for a project's RuleGarden state."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from rulegarden.models import EvidenceEvent, RuleDocument, TaskState, Transaction


class StorageError(RuntimeError):
    """Raised when persisted RuleGarden state cannot be safely read."""


_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9-]{1,63}$")


class RuleRepository:
    """Own the `.rulegarden` files for one target project directory."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.rulegarden_dir = self.project_root / ".rulegarden"
        self.runtime_dir = self.rulegarden_dir / "runtime"
        self.rules_path = self.rulegarden_dir / "rules.yaml"
        self.evidence_path = self.rulegarden_dir / "evidence.jsonl"
        self.history_path = self.rulegarden_dir / "history.jsonl"
        self.state_path = self.rulegarden_dir / "state.json"

    def initialize_storage(self) -> None:
        """Create the minimal layout without changing any unrelated project file."""
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        gitignore_path = self.rulegarden_dir / ".gitignore"
        if not gitignore_path.exists():
            self._atomic_write(gitignore_path, "runtime/\n")
        if not self.rules_path.exists():
            self.save_rules(RuleDocument())
        for filename in ("evidence.jsonl", "history.jsonl"):
            (self.rulegarden_dir / filename).touch(exist_ok=True)

    def load_rules(self) -> RuleDocument:
        """Read and validate the source-of-truth YAML without mutating it on error."""
        if not self.rules_path.exists():
            return RuleDocument()
        try:
            data = yaml.safe_load(self.rules_path.read_text(encoding="utf-8"))
            return RuleDocument.model_validate(data or {})
        except (OSError, yaml.YAMLError, ValidationError) as error:
            raise StorageError(f"cannot read {self.rules_path}: {error}") from error

    def save_rules(self, document: RuleDocument) -> None:
        """Validate and atomically replace `rules.yaml` only after serialization succeeds."""
        payload = yaml.safe_dump(
            document.model_dump(mode="json"),
            allow_unicode=True,
            sort_keys=False,
        )
        self.rulegarden_dir.mkdir(parents=True, exist_ok=True)
        self._atomic_write(self.rules_path, payload)

    def append_evidence(self, event: EvidenceEvent) -> None:
        """Append a redacted event as a compact JSONL record."""
        self.rulegarden_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        with self.evidence_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{line}\n")
            handle.flush()
            os.fsync(handle.fileno())

    def append_history(self, transaction: Transaction) -> None:
        """Append a complete transaction record only after all visible writes succeed."""
        self.rulegarden_dir.mkdir(parents=True, exist_ok=True)
        line = json.dumps(transaction.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        with self.history_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(f"{line}\n")
            handle.flush()
            os.fsync(handle.fileno())

    def load_history(self) -> list[Transaction]:
        """Read the append-only transaction journal, rejecting partial or invalid entries."""
        if not self.history_path.exists():
            return []
        try:
            return [
                Transaction.model_validate_json(line)
                for line in self.history_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except (OSError, ValidationError) as error:
            raise StorageError(f"cannot read {self.history_path}: {error}") from error

    def save_task_state(self, state: TaskState) -> None:
        """Persist only transient task metadata under the ignored runtime directory."""
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(state.model_dump(mode="json"), ensure_ascii=False, separators=(",", ":"))
        self._atomic_write(self._state_path(state.task_id), payload)

    def load_task_state(self, task_id: str) -> TaskState | None:
        """Load a transient task state or return `None` after normal cleanup."""
        path = self._state_path(task_id)
        if not path.exists():
            return None
        try:
            return TaskState.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError) as error:
            raise StorageError(f"cannot read {path}: {error}") from error

    def delete_task_state(self, task_id: str) -> None:
        """Remove the transient state once a task completes or is abandoned."""
        path = self._state_path(task_id)
        if path.exists():
            path.unlink()

    def set_current_task(self, task_id: str) -> None:
        """Store the active task identifier without copying prompt content into shared state."""
        self._state_path(task_id)
        self._write_project_state({"current_task_id": task_id, "stop_notified": False})

    def get_current_task_id(self) -> str | None:
        """Return the active task identifier, treating an absent state file as no active task."""
        current = self._read_project_state().get("current_task_id")
        if current is None:
            return None
        if not isinstance(current, str) or not _IDENTIFIER.fullmatch(current):
            raise StorageError("current task id is invalid")
        return current

    def mark_stop_notified(self, task_id: str) -> bool:
        """Return true once per active task so Stop hooks cannot recurse indefinitely."""
        state = self._read_project_state()
        if state.get("current_task_id") != task_id or state.get("stop_notified") is True:
            return False
        state["stop_notified"] = True
        self._write_project_state(state)
        return True

    def clear_current_task(self, task_id: str) -> None:
        """Clear the pointer only when the finishing task still owns it."""
        state = self._read_project_state()
        if state.get("current_task_id") == task_id:
            self._atomic_write(self.state_path, "{}")

    def _state_path(self, task_id: str) -> Path:
        """Reject path traversal before mapping a task identifier to a file name."""
        if not _IDENTIFIER.fullmatch(task_id):
            raise StorageError("task id is invalid")
        return self.runtime_dir / f"{task_id}.json"

    def _read_project_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            state = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StorageError(f"cannot read {self.state_path}: {error}") from error
        if not isinstance(state, dict):
            raise StorageError("project state must be a JSON object")
        return state

    def _write_project_state(self, state: dict[str, Any]) -> None:
        self._atomic_write(self.state_path, json.dumps(state, ensure_ascii=False, separators=(",", ":")))

    @staticmethod
    def _atomic_write(target: Path, contents: str) -> None:
        """Replace a file only after its complete new contents are durable on disk."""
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                delete=False,
                dir=target.parent,
                prefix=f".{target.name}.",
                suffix=".tmp",
            ) as handle:
                temporary_name = handle.name
                handle.write(contents)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, target)
            temporary_name = None
        finally:
            if temporary_name is not None:
                Path(temporary_name).unlink(missing_ok=True)
