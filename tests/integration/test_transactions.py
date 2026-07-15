"""End-to-end reversible rule transaction tests."""

from __future__ import annotations

import importlib
import subprocess
from pathlib import Path

import pytest

from rulegarden.models import Rule, RuleDocument, RuleStatus


def _transactions_module():
    """Load the future transaction service inside tests for a clear RED failure."""
    try:
        return importlib.import_module("rulegarden.transactions.service")
    except ModuleNotFoundError as error:
        pytest.fail(f"transaction service has not been implemented: {error}")


def _initialize_git_repository(project_root: Path) -> None:
    """Exercise the service inside the Git project shape it targets."""
    subprocess.run(["git", "init", "-q"], cwd=project_root, check=True)


def test_rule_update_and_undo_restore_rules_and_agents_block(tmp_path: Path) -> None:
    transactions = _transactions_module()
    _initialize_git_repository(tmp_path)
    service = transactions.TransactionService(tmp_path)
    service.initialize()
    baseline_agents = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    baseline_rules = service.repository.load_rules()
    promoted = Rule(
        id="minimal-scope",
        instruction="Modify only relevant files.",
        status=RuleStatus.STABLE,
    )

    transaction = service.apply_rule_update(
        operation="promote-minimal-scope",
        next_rules=RuleDocument(rules=[promoted]),
        rule_ids=[promoted.id],
    )

    assert transaction.after_rules.rules[0].status is RuleStatus.STABLE
    assert "Modify only relevant files." in (tmp_path / "AGENTS.md").read_text(encoding="utf-8")

    service.undo()

    assert service.repository.load_rules() == baseline_rules
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == baseline_agents


def test_undo_preserves_user_changes_outside_the_managed_block(tmp_path: Path) -> None:
    transactions = _transactions_module()
    service = transactions.TransactionService(tmp_path)
    service.initialize()
    stable_rule = Rule(id="reuse-code", instruction="Inspect existing code first.", status=RuleStatus.STABLE)
    service.apply_rule_update("add-stable-rule", RuleDocument(rules=[stable_rule]), [stable_rule.id])
    agents_path = tmp_path / "AGENTS.md"
    agents_path.write_text(
        f"{agents_path.read_text(encoding='utf-8')}\nUser-owned footer added after the transaction.\n",
        encoding="utf-8",
    )

    service.undo()

    restored = agents_path.read_text(encoding="utf-8")
    assert "User-owned footer added after the transaction." in restored
    assert "Inspect existing code first." not in restored


def test_failed_agents_write_rolls_back_the_rules_document(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    transactions = _transactions_module()
    service = transactions.TransactionService(tmp_path)
    service.initialize()
    baseline_rules = service.repository.load_rules()
    stable_rule = Rule(id="reuse-code", instruction="Inspect existing code first.", status=RuleStatus.STABLE)

    def fail_agents_write(_: str) -> None:
        raise OSError("simulated AGENTS.md write failure")

    monkeypatch.setattr(service, "_write_agents", fail_agents_write)

    with pytest.raises(transactions.TransactionError, match="could not apply"):
        service.apply_rule_update("add-stable-rule", RuleDocument(rules=[stable_rule]), [stable_rule.id])

    assert service.repository.load_rules() == baseline_rules
