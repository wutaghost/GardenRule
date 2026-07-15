"""Validation contracts for durable RuleGarden data."""

from __future__ import annotations

import importlib

import pytest
from pydantic import ValidationError


def _models():
    """Load the future model module inside tests so RED remains an assertion failure."""
    try:
        return importlib.import_module("rulegarden.models")
    except ModuleNotFoundError as error:
        pytest.fail(f"rulegarden.models has not been implemented: {error}")


def test_rule_rejects_unknown_status() -> None:
    models = _models()

    with pytest.raises(ValidationError):
        models.Rule(id="minimal-scope", instruction="Modify only relevant files.", status="permanent")


def test_rule_rejects_unknown_enforcement() -> None:
    models = _models()

    with pytest.raises(ValidationError):
        models.Rule(id="minimal-scope", instruction="Modify only relevant files.", enforcement="force")


def test_rule_requires_nonempty_instruction() -> None:
    models = _models()

    with pytest.raises(ValidationError):
        models.Rule(id="minimal-scope", instruction="   ")


def test_rule_document_rejects_duplicate_ids() -> None:
    models = _models()
    rule = models.Rule(id="minimal-scope", instruction="Modify only relevant files.")

    with pytest.raises(ValidationError):
        models.RuleDocument(rules=[rule, rule])


def test_evidence_event_rejects_raw_prompt_fields() -> None:
    models = _models()

    with pytest.raises(ValidationError):
        models.EvidenceEvent(
            event_id="evt-001",
            rule_id="minimal-scope",
            type="user_correction",
            summary="User requested a narrower change.",
            prompt="Do not store this full prompt.",
        )
