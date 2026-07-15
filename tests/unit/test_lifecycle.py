"""Explicit lifecycle transition tests for individual project rules."""

from __future__ import annotations

import importlib

import pytest

from rulegarden.models import Rule, RuleDocument, RuleStatus


def _lifecycle_module():
    """Load the future lifecycle module inside tests so missing code is a RED failure."""
    try:
        return importlib.import_module("rulegarden.rules.lifecycle")
    except ModuleNotFoundError as error:
        pytest.fail(f"rule lifecycle has not been implemented: {error}")


def test_learned_rules_start_dynamic() -> None:
    lifecycle = _lifecycle_module()

    rule = lifecycle.create_learned_rule("minimal-scope", "Modify only relevant files.")

    assert rule.status is RuleStatus.DYNAMIC
    assert rule.source_type.value == "learned"


def test_promote_records_the_prior_status() -> None:
    lifecycle = _lifecycle_module()
    document = RuleDocument(rules=[Rule(id="minimal-scope", instruction="Modify only relevant files.")])

    updated = lifecycle.transition_rule(document, "minimal-scope", RuleStatus.STABLE)

    assert updated.rules[0].status is RuleStatus.STABLE
    assert updated.rules[0].previous_status is RuleStatus.DYNAMIC


def test_disable_and_enable_restores_the_previous_lifecycle_state() -> None:
    lifecycle = _lifecycle_module()
    document = RuleDocument(rules=[Rule(id="minimal-scope", instruction="Modify only relevant files.", status=RuleStatus.STABLE)])

    disabled = lifecycle.disable_rule(document, "minimal-scope")
    enabled = lifecycle.enable_rule(disabled, "minimal-scope")

    assert disabled.rules[0].enabled is False
    assert disabled.rules[0].status is RuleStatus.DISABLED
    assert enabled.rules[0].enabled is True
    assert enabled.rules[0].status is RuleStatus.STABLE


def test_deleted_rules_cannot_transition_back_to_active_state() -> None:
    lifecycle = _lifecycle_module()
    deleted = RuleDocument(
        rules=[Rule(id="minimal-scope", instruction="Modify only relevant files.", status=RuleStatus.DELETED, enabled=False)]
    )

    with pytest.raises(lifecycle.LifecycleError, match="cannot transition"):
        lifecycle.transition_rule(deleted, "minimal-scope", RuleStatus.STABLE)


def test_add_rule_rejects_duplicate_ids() -> None:
    lifecycle = _lifecycle_module()
    existing = Rule(id="minimal-scope", instruction="Modify only relevant files.")

    with pytest.raises(lifecycle.LifecycleError, match="already exists"):
        lifecycle.add_rule(RuleDocument(rules=[existing]), existing)
