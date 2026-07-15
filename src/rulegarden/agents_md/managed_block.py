"""Render and replace the isolated RuleGarden-managed block in AGENTS.md."""

from __future__ import annotations

from collections.abc import Iterable

from rulegarden.models import RiskLevel, Rule, RuleStatus


START_MARKER = "<!-- RULEGARDEN:START -->"
END_MARKER = "<!-- RULEGARDEN:END -->"
_RISK_ORDER = {
    RiskLevel.CRITICAL: 0,
    RiskLevel.HIGH: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.LOW: 3,
}


class ManagedBlockError(ValueError):
    """Raised when markers are malformed or compilation exceeds its budget."""


def render_stable_block(rules: Iterable[Rule], byte_budget: int = 8_192) -> str:
    """Compile enabled stable rules into a bounded, deterministic AGENTS section."""
    selected = [rule for rule in rules if rule.enabled and rule.status is RuleStatus.STABLE]
    selected.sort(key=lambda rule: (_RISK_ORDER[rule.risk_level], rule.created_at, rule.id))

    lines = [START_MARKER, "## RuleGarden Stable Rules", ""]
    lines.extend(f"- {rule.instruction}" for rule in selected)
    lines.append(END_MARKER)
    block = "\n".join(lines)
    if len(block.encode("utf-8")) > byte_budget:
        raise ManagedBlockError(f"compiled RuleGarden block exceeds the {byte_budget}-byte budget")
    return block


def extract_managed_block(document: str) -> str | None:
    """Return the exact existing marked section or `None` when not initialized."""
    span = _managed_span(document)
    if span is None:
        return None
    start, end = span
    return document[start:end]


def replace_managed_block(document: str, replacement: str) -> str:
    """Insert or replace only RuleGarden's marked range, preserving all other bytes."""
    replacement_span = _managed_span(replacement)
    if replacement_span is None or replacement_span != (0, len(replacement)):
        raise ManagedBlockError("replacement must contain one complete RuleGarden block")

    span = _managed_span(document)
    if span is None:
        if not document:
            return f"{replacement}\n"
        separator = "" if document.endswith("\n\n") else "\n"
        return f"{document}{separator}{replacement}\n"

    start, end = span
    return f"{document[:start]}{replacement}{document[end:]}"


def _managed_span(document: str) -> tuple[int, int] | None:
    """Validate markers before any edit so malformed user files are never guessed at."""
    start_count = document.count(START_MARKER)
    end_count = document.count(END_MARKER)
    if start_count == 0 and end_count == 0:
        return None
    if start_count == 0 or end_count == 0:
        raise ManagedBlockError("RuleGarden markers must be paired")
    if start_count != 1 or end_count != 1:
        raise ManagedBlockError("RuleGarden markers must appear exactly once")

    start = document.index(START_MARKER)
    end = document.index(END_MARKER)
    if end < start:
        raise ManagedBlockError("RuleGarden end marker must follow the start marker")
    return start, end + len(END_MARKER)
