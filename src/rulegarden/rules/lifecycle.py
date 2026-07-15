"""Explicit lifecycle transitions for project rules."""

from __future__ import annotations

from datetime import datetime, timezone

from rulegarden.models import Rule, RuleDocument, RuleStatus, SourceType


class LifecycleError(ValueError):
    """Raised when a requested rule mutation violates lifecycle invariants."""


_ALLOWED_TRANSITIONS: dict[RuleStatus, set[RuleStatus]] = {
    RuleStatus.DYNAMIC: {RuleStatus.STABLE, RuleStatus.LOW_EFFECT},
    RuleStatus.STABLE: {RuleStatus.DYNAMIC, RuleStatus.LOW_EFFECT},
    RuleStatus.LOW_EFFECT: {RuleStatus.DYNAMIC, RuleStatus.STABLE},
    RuleStatus.DISABLED: set(),
    RuleStatus.DELETED: set(),
}


def create_learned_rule(identifier: str, instruction: str) -> Rule:
    """Create a learned rule in the only safe initial lifecycle state: dynamic."""
    return Rule(id=identifier, instruction=instruction, source_type=SourceType.LEARNED, status=RuleStatus.DYNAMIC)


def add_rule(document: RuleDocument, rule: Rule) -> RuleDocument:
    """Add one rule while rejecting an ambiguous duplicate identity."""
    if any(existing.id == rule.id for existing in document.rules):
        raise LifecycleError(f"rule '{rule.id}' already exists")
    return RuleDocument(version=document.version, rules=[*document.rules, rule.model_copy(deep=True)])


def transition_rule(document: RuleDocument, rule_id: str, target_status: RuleStatus) -> RuleDocument:
    """Move an active rule between dynamic, stable, and low-effect states."""
    index, rule = _find_rule(document, rule_id)
    if rule.status is RuleStatus.DELETED:
        raise LifecycleError(f"cannot transition deleted rule '{rule_id}'")
    if target_status is RuleStatus.DISABLED:
        return disable_rule(document, rule_id)
    if target_status is RuleStatus.DELETED:
        return delete_rule(document, rule_id)
    if rule.status is RuleStatus.DISABLED:
        raise LifecycleError(f"cannot transition disabled rule '{rule_id}'; enable it first")
    if target_status is rule.status:
        return document.model_copy(deep=True)
    if target_status not in _ALLOWED_TRANSITIONS[rule.status]:
        raise LifecycleError(f"cannot transition {rule.status.value} rule '{rule_id}' to {target_status.value}")
    return _replace_rule(
        document,
        index,
        _with_status(rule, target_status, enabled=True, previous_status=rule.status),
    )


def disable_rule(document: RuleDocument, rule_id: str) -> RuleDocument:
    """Disable a rule while retaining the state needed by a future enable command."""
    index, rule = _find_rule(document, rule_id)
    if rule.status is RuleStatus.DELETED:
        raise LifecycleError(f"cannot disable deleted rule '{rule_id}'")
    if rule.status is RuleStatus.DISABLED:
        return document.model_copy(deep=True)
    disabled = _with_status(rule, RuleStatus.DISABLED, enabled=False, previous_status=rule.status)
    return _replace_rule(document, index, disabled)


def enable_rule(document: RuleDocument, rule_id: str) -> RuleDocument:
    """Restore a disabled rule to the state it had before it was disabled."""
    index, rule = _find_rule(document, rule_id)
    if rule.status is not RuleStatus.DISABLED:
        raise LifecycleError(f"rule '{rule_id}' is not disabled")
    restored_status = rule.previous_status or RuleStatus.DYNAMIC
    restored = _with_status(rule, restored_status, enabled=True, previous_status=None)
    return _replace_rule(document, index, restored)


def delete_rule(document: RuleDocument, rule_id: str) -> RuleDocument:
    """Tombstone a rule so history remains recoverable but it can never be selected."""
    index, rule = _find_rule(document, rule_id)
    if rule.status is RuleStatus.DELETED:
        return document.model_copy(deep=True)
    deleted = _with_status(rule, RuleStatus.DELETED, enabled=False, previous_status=rule.status)
    return _replace_rule(document, index, deleted)


def _find_rule(document: RuleDocument, rule_id: str) -> tuple[int, Rule]:
    for index, rule in enumerate(document.rules):
        if rule.id == rule_id:
            return index, rule
    raise LifecycleError(f"rule '{rule_id}' does not exist")


def _with_status(
    rule: Rule,
    status: RuleStatus,
    *,
    enabled: bool,
    previous_status: RuleStatus | None = None,
) -> Rule:
    now = datetime.now(timezone.utc)
    return rule.model_copy(
        update={
            "status": status,
            "enabled": enabled,
            "previous_status": previous_status,
            "updated_at": now,
        }
    )


def _replace_rule(document: RuleDocument, index: int, replacement: Rule) -> RuleDocument:
    rules = [rule.model_copy(deep=True) for rule in document.rules]
    rules[index] = replacement
    return RuleDocument(version=document.version, rules=rules)
