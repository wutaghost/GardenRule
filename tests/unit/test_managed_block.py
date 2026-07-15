"""Tests for the isolated RuleGarden section in AGENTS.md."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from rulegarden.models import RiskLevel, Rule, RuleStatus


def _managed_block_module():
    """Load the future module inside tests so a missing implementation is a RED failure."""
    try:
        return importlib.import_module("rulegarden.agents_md.managed_block")
    except ModuleNotFoundError as error:
        pytest.fail(f"managed block support has not been implemented: {error}")


def _stable_rule(identifier: str, instruction: str, risk: RiskLevel = RiskLevel.MEDIUM) -> Rule:
    return Rule(id=identifier, instruction=instruction, status=RuleStatus.STABLE, risk_level=risk)


def test_inserts_a_managed_block_without_rewriting_existing_instructions() -> None:
    managed = _managed_block_module()
    original = "# Existing Project Instructions\n\nKeep this content untouched.\n"
    block = managed.render_stable_block([_stable_rule("minimal-scope", "Modify only relevant files.")])

    updated = managed.replace_managed_block(original, block)

    assert updated.startswith(original.rstrip("\n"))
    assert managed.START_MARKER in updated
    assert "- Modify only relevant files." in updated
    assert updated.endswith("\n")


def test_replaces_only_the_existing_marked_span() -> None:
    managed = _managed_block_module()
    fixture = Path(__file__).parents[1] / "fixtures" / "agents_with_user_content.md"
    original = fixture.read_text(encoding="utf-8")
    before = original[: original.index(managed.START_MARKER)]
    after = original[original.index(managed.END_MARKER) + len(managed.END_MARKER) :]
    replacement = managed.render_stable_block([_stable_rule("reuse-code", "Inspect existing code first.")])

    updated = managed.replace_managed_block(original, replacement)

    assert updated.startswith(before)
    assert updated.endswith(after)
    assert "Existing stable rule." not in updated
    assert "Inspect existing code first." in updated


def test_rejects_duplicate_or_unpaired_markers() -> None:
    managed = _managed_block_module()

    with pytest.raises(managed.ManagedBlockError, match="exactly once"):
        managed.replace_managed_block(
            "<!-- RULEGARDEN:START --><!-- RULEGARDEN:START --><!-- RULEGARDEN:END -->",
            managed.render_stable_block([]),
        )

    with pytest.raises(managed.ManagedBlockError, match="paired"):
        managed.replace_managed_block("<!-- RULEGARDEN:START -->", managed.render_stable_block([]))


def test_rendered_block_is_a_noop_when_the_stable_rules_are_unchanged() -> None:
    managed = _managed_block_module()
    block = managed.render_stable_block([_stable_rule("minimal-scope", "Modify only relevant files.")])
    original = f"# Notes\n\n{block}\n"

    assert managed.replace_managed_block(original, block) == original


def test_replacing_with_the_prior_block_restores_the_original_document() -> None:
    managed = _managed_block_module()
    fixture = Path(__file__).parents[1] / "fixtures" / "agents_with_user_content.md"
    original = fixture.read_text(encoding="utf-8")
    before_change = managed.extract_managed_block(original)
    assert before_change is not None

    changed = managed.replace_managed_block(
        original,
        managed.render_stable_block([_stable_rule("minimal-scope", "Modify only relevant files.")]),
    )

    assert managed.replace_managed_block(changed, before_change) == original


def test_compilation_filters_disabled_dynamic_rules_and_respects_byte_budget() -> None:
    managed = _managed_block_module()
    selected = _stable_rule("high-risk", "Protect credentials.", RiskLevel.HIGH)
    hidden = Rule(id="dynamic", instruction="Do not render.")
    disabled = _stable_rule("disabled", "Do not render either.")
    disabled.enabled = False

    block = managed.render_stable_block([hidden, disabled, selected])

    assert "Protect credentials." in block
    assert "Do not render" not in block
    with pytest.raises(managed.ManagedBlockError, match="budget"):
        managed.render_stable_block([selected], byte_budget=10)
