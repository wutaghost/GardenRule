"""Deterministic selection of rules relevant to one task."""

from __future__ import annotations

import posixpath
from datetime import datetime, timezone
from collections.abc import Iterable, Set

from rulegarden.models import Rule, RuleDocument, RuleStatus


def select_rules(
    rules: Iterable[Rule],
    task_types: Iterable[str],
    expected_paths: Iterable[str],
) -> list[Rule]:
    """Return active dynamic and stable rules whose populated scope dimensions match."""
    normalized_types = {_normalize_task_type(task_type) for task_type in task_types}
    normalized_paths = [_normalize_path(path) for path in expected_paths]
    return [
        rule
        for rule in rules
        if rule.enabled
        and rule.status in {RuleStatus.DYNAMIC, RuleStatus.STABLE}
        and _matches_scope(rule, normalized_types, normalized_paths)
    ]


def record_rule_hits(document: RuleDocument, selected_ids: Set[str]) -> RuleDocument:
    """Return a new document with hit metrics updated only for rules returned to a task."""
    now = datetime.now(timezone.utc)
    updated_rules: list[Rule] = []
    for rule in document.rules:
        if rule.id not in selected_ids:
            updated_rules.append(rule.model_copy(deep=True))
            continue
        metrics = rule.metrics.model_copy(update={"hit_count": rule.metrics.hit_count + 1})
        updated_rules.append(rule.model_copy(update={"metrics": metrics, "last_hit_at": now, "updated_at": now}))
    return RuleDocument(version=document.version, rules=updated_rules)


def _matches_scope(rule: Rule, task_types: set[str], expected_paths: list[str]) -> bool:
    """Apply AND semantics across populated dimensions and OR semantics within each one."""
    scoped_types = {_normalize_task_type(task_type) for task_type in rule.scope.task_types}
    if scoped_types and not scoped_types.intersection(task_types):
        return False

    scoped_paths = [_normalize_path(path) for path in rule.scope.paths]
    if scoped_paths and not any(_path_matches(scope_path, path) for scope_path in scoped_paths for path in expected_paths):
        return False
    return True


def _normalize_task_type(task_type: str) -> str:
    return task_type.strip().casefold()


def _normalize_path(path: str) -> str:
    """Normalize slash and case differences so Windows task paths match stored scopes."""
    normalized = posixpath.normpath(path.replace("\\", "/").strip()).lstrip("./")
    return normalized.casefold()


def _path_matches(scope_path: str, candidate_path: str) -> bool:
    return candidate_path == scope_path or candidate_path.startswith(f"{scope_path.rstrip('/')}/")
