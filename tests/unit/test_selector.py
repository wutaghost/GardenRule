"""Deterministic task-to-rule matching tests."""

from __future__ import annotations

import importlib

import pytest

from rulegarden.models import Rule, RuleDocument, RuleScope, RuleStatus


def _selector_module():
    """Load the future selector inside tests so missing code remains a RED failure."""
    try:
        return importlib.import_module("rulegarden.rules.selector")
    except ModuleNotFoundError as error:
        pytest.fail(f"rule selector has not been implemented: {error}")


def test_selects_a_directory_scoped_rule_for_windows_style_paths() -> None:
    selector = _selector_module()
    rule = Rule(
        id="api-tests",
        instruction="Run API tests first.",
        scope=RuleScope(paths=["src/api"]),
    )

    selected = selector.select_rules([rule], task_types=[], expected_paths=["src\\api\\users.py"])

    assert [item.id for item in selected] == ["api-tests"]


def test_scope_requires_all_populated_scope_dimensions_to_match() -> None:
    selector = _selector_module()
    rule = Rule(
        id="api-bugfix",
        instruction="Preserve API compatibility.",
        scope=RuleScope(paths=["src/api"], task_types=["bugfix"]),
    )

    assert selector.select_rules([rule], task_types=["bugfix"], expected_paths=["src/api/users.py"])
    assert not selector.select_rules([rule], task_types=["feature"], expected_paths=["src/api/users.py"])
    assert not selector.select_rules([rule], task_types=["bugfix"], expected_paths=["src/web/page.ts"])


def test_selection_includes_active_dynamic_and_stable_rules_only() -> None:
    selector = _selector_module()
    dynamic = Rule(id="dynamic", instruction="Dynamic rule.")
    stable = Rule(id="stable", instruction="Stable rule.", status=RuleStatus.STABLE)
    disabled = Rule(id="disabled", instruction="Disabled rule.", enabled=False)
    deleted = Rule(id="deleted", instruction="Deleted rule.", status=RuleStatus.DELETED)

    selected = selector.select_rules([dynamic, stable, disabled, deleted], task_types=[], expected_paths=[])

    assert [item.id for item in selected] == ["dynamic", "stable"]


def test_record_rule_hits_updates_only_selected_rules() -> None:
    selector = _selector_module()
    selected = Rule(id="selected", instruction="Selected rule.")
    unselected = Rule(id="unselected", instruction="Unselected rule.")
    document = RuleDocument(rules=[selected, unselected])

    updated = selector.record_rule_hits(document, selected_ids={"selected"})

    assert updated.rules[0].metrics.hit_count == 1
    assert updated.rules[1].metrics.hit_count == 0
