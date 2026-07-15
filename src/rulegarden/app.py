"""Transport-independent application service for RuleGarden workflows."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from rulegarden.models import (
    EvidenceEvent,
    EvidenceEventType,
    RiskLevel,
    Rule,
    RuleDocument,
    RuleScope,
    RuleStatus,
    SourceType,
    TaskState,
)
from rulegarden.rules.lifecycle import (
    add_rule,
    create_learned_rule,
    delete_rule,
    disable_rule,
    enable_rule,
    transition_rule,
)
from rulegarden.rules.selector import record_rule_hits, select_rules
from rulegarden.transactions.service import TransactionService


class ApplicationError(ValueError):
    """Raised for invalid task or command requests before a transport formats them."""


_RISK_BY_SEVERITY = {
    "low": RiskLevel.LOW,
    "normal": RiskLevel.MEDIUM,
    "medium": RiskLevel.MEDIUM,
    "high": RiskLevel.HIGH,
    "critical": RiskLevel.CRITICAL,
}


class RuleGardenApplication:
    """Expose one deterministic workflow to CLI, MCP tools, and future Hook adapters."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.transactions = TransactionService(self.project_root)
        self.repository = self.transactions.repository

    def initialize(self) -> dict[str, Any]:
        """Initialize persistent state and the non-destructive AGENTS.md managed block."""
        self.transactions.initialize()
        return {
            "initialized": True,
            "project_root": str(self.project_root.resolve()),
            "rule_count": len(self.repository.load_rules().rules),
        }

    def begin_task(
        self,
        task_summary: str,
        task_types: list[str],
        expected_paths: list[str],
        risk_signals: list[str],
    ) -> dict[str, Any]:
        """Create ignored runtime state and return only task-relevant rule guidance."""
        if not task_summary.strip():
            raise ApplicationError("task summary must not be blank")
        self.transactions.initialize()
        document = self.repository.load_rules()
        selected = select_rules(document.rules, task_types, expected_paths)
        selected_ids = {rule.id for rule in selected}
        if selected_ids:
            self.repository.save_rules(record_rule_hits(document, selected_ids))
        task = TaskState(
            task_id=f"task-{uuid4().hex}",
            task_summary=task_summary.strip(),
            task_types=task_types,
            expected_paths=expected_paths,
            risk_signals=risk_signals,
            selected_rule_ids=[rule.id for rule in selected],
        )
        self.repository.save_task_state(task)
        return {"task_id": task.task_id, "rules": [_rule_view(rule) for rule in selected]}

    def record_correction(
        self,
        task_id: str,
        candidate_instruction: str,
        scope: RuleScope | dict[str, Any] | None,
        evidence_summary: str,
        affected_paths: list[str],
        severity: str,
    ) -> dict[str, Any]:
        """Create a dynamic learned rule and redacted evidence for an active task."""
        if self.repository.load_task_state(task_id) is None:
            raise ApplicationError(f"task '{task_id}' does not exist or has already finished")
        if not evidence_summary.strip():
            raise ApplicationError("evidence summary must not be blank")
        try:
            risk_level = _RISK_BY_SEVERITY[severity.strip().casefold()]
        except KeyError as error:
            raise ApplicationError(f"unsupported correction severity '{severity}'") from error
        rule_scope = RuleScope.model_validate(scope or {})
        current = self.repository.load_rules()
        identifier = _next_rule_id(candidate_instruction, {rule.id for rule in current.rules})
        rule = create_learned_rule(identifier, candidate_instruction).model_copy(
            update={"scope": rule_scope, "risk_level": risk_level}
        )
        updated = add_rule(current, rule)
        self.transactions.apply_rule_update("record-correction", updated, [rule.id])
        event = EvidenceEvent(
            event_id=f"evt-{uuid4().hex}",
            rule_id=rule.id,
            type=EvidenceEventType.USER_CORRECTION,
            summary=evidence_summary.strip(),
            paths=affected_paths,
            task_id=task_id,
        )
        self.repository.append_evidence(event)
        return _rule_view(rule)

    def finish_task(self, task_id: str) -> dict[str, Any]:
        """Remove ephemeral task data even when a caller cannot consume the summary."""
        task = self.repository.load_task_state(task_id)
        if task is None:
            raise ApplicationError(f"task '{task_id}' does not exist or has already finished")
        try:
            return {
                "task_id": task.task_id,
                "finished": True,
                "selected_rule_ids": task.selected_rule_ids,
                "touched_paths": task.touched_paths,
            }
        finally:
            self.repository.delete_task_state(task_id)

    def list_rules(self, status: RuleStatus | str | None = None) -> dict[str, Any]:
        """List rule summaries without exposing evidence, metrics, or runtime data."""
        selected_status = _coerce_status(status) if status is not None else None
        rules = self.repository.load_rules().rules
        if selected_status is not None:
            rules = [rule for rule in rules if rule.status is selected_status]
        return {"rules": [_rule_view(rule) for rule in rules]}

    def transition_rule(self, rule_id: str, target_status: RuleStatus | str) -> dict[str, Any]:
        """Apply an explicit lifecycle change as a reversible compiled-rule transaction."""
        target = _coerce_status(target_status)
        current = self.repository.load_rules()
        if target is RuleStatus.DISABLED:
            updated = disable_rule(current, rule_id)
        elif target is RuleStatus.DELETED:
            updated = delete_rule(current, rule_id)
        elif target is RuleStatus.DYNAMIC and _rule_status(current, rule_id) is RuleStatus.DISABLED:
            updated = enable_rule(current, rule_id)
        else:
            updated = transition_rule(current, rule_id, target)
        transaction = self.transactions.apply_rule_update(f"transition:{rule_id}:{target.value}", updated, [rule_id])
        changed = next(rule for rule in updated.rules if rule.id == rule_id)
        return {**_rule_view(changed), "transaction_id": transaction.transaction_id}

    def undo(self, transaction_id: str | None = None) -> dict[str, Any]:
        """Undo the requested transaction after transaction-level concurrency checks."""
        transaction = self.transactions.undo(transaction_id)
        return {"transaction_id": transaction.transaction_id, "operation": transaction.operation, "undone": True}


def _rule_view(rule: Rule) -> dict[str, Any]:
    """Keep MCP task responses limited to actionable rule guidance."""
    return {
        "id": rule.id,
        "instruction": rule.instruction,
        "exceptions": rule.exceptions,
        "risk": rule.risk_level.value,
        "status": rule.status.value,
    }


def _coerce_status(status: RuleStatus | str) -> RuleStatus:
    try:
        return status if isinstance(status, RuleStatus) else RuleStatus(status)
    except ValueError as error:
        raise ApplicationError(f"unsupported rule status '{status}'") from error


def _rule_status(document: RuleDocument, rule_id: str) -> RuleStatus:
    for rule in document.rules:
        if rule.id == rule_id:
            return rule.status
    raise ApplicationError(f"rule '{rule_id}' does not exist")


def _next_rule_id(instruction: str, existing_ids: set[str]) -> str:
    """Derive a readable identifier while resolving collisions without replacing prior rules."""
    base = re.sub(r"[^a-z0-9]+", "-", instruction.casefold()).strip("-") or "learned-rule"
    if len(base) < 2:
        base = f"{base}-rule"
    base = base[:63].rstrip("-")
    candidate = base
    number = 2
    while candidate in existing_ids:
        suffix = f"-{number}"
        candidate = f"{base[: 64 - len(suffix)]}{suffix}".rstrip("-")
        number += 1
    return candidate
