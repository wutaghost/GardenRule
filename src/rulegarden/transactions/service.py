"""Coordinate reversible updates across rules.yaml and AGENTS.md."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from rulegarden.agents_md.managed_block import (
    ManagedBlockError,
    extract_managed_block,
    render_stable_block,
    replace_managed_block,
)
from rulegarden.models import RuleDocument, Transaction
from rulegarden.storage.repository import RuleRepository


class TransactionError(RuntimeError):
    """Raised when a multi-file RuleGarden transaction cannot complete safely."""


class TransactionConflict(TransactionError):
    """Raised when a file changed after the transaction and cannot be safely undone."""


class TransactionService:
    """Apply and undo RuleGarden-owned updates without rewriting user-owned AGENTS text."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)
        self.repository = RuleRepository(self.project_root)
        self.agents_path = self.project_root / "AGENTS.md"

    def initialize(self) -> None:
        """Create storage and an empty managed block before later transactions mutate it."""
        self.repository.initialize_storage()
        current_agents = self._read_agents()
        try:
            if extract_managed_block(current_agents) is None:
                self._write_agents(replace_managed_block(current_agents, render_stable_block([])))
        except ManagedBlockError as error:
            raise TransactionError(f"cannot initialize AGENTS.md: {error}") from error

    def apply_rule_update(
        self,
        operation: str,
        next_rules: RuleDocument,
        rule_ids: list[str],
    ) -> Transaction:
        """Persist a validated rule update and its compiled AGENTS block as one transaction."""
        if not operation.strip():
            raise TransactionError("transaction operation must not be blank")
        before_rules = self.repository.load_rules()
        agents_before = self._read_agents()
        try:
            block_before = extract_managed_block(agents_before)
            if block_before is None:
                raise TransactionError("RuleGarden has not initialized AGENTS.md")
            block_after = render_stable_block(next_rules.rules)
            agents_after = replace_managed_block(agents_before, block_after)
        except ManagedBlockError as error:
            raise TransactionError(f"cannot compile AGENTS.md: {error}") from error

        transaction = Transaction(
            transaction_id=f"txn-{uuid4().hex}",
            operation=operation.strip(),
            rule_ids=rule_ids,
            before_rules=before_rules,
            after_rules=next_rules,
            agents_block_before=block_before,
            agents_block_after=block_after,
        )
        try:
            self.repository.save_rules(next_rules)
            self._write_agents(agents_after)
            self.repository.append_history(transaction)
        except Exception as error:
            recovery_error = self._restore_after_failed_apply(before_rules, agents_before)
            detail = f"; recovery also failed: {recovery_error}" if recovery_error else ""
            raise TransactionError(f"could not apply RuleGarden transaction: {error}{detail}") from error
        return transaction

    def undo(self, transaction_id: str | None = None) -> Transaction:
        """Undo the latest matching transaction while preserving external AGENTS edits."""
        history = self.repository.load_history()
        if not history:
            raise TransactionError("no RuleGarden transaction is available to undo")
        target = self._find_transaction(history, transaction_id)
        current_rules = self.repository.load_rules()
        if current_rules != target.after_rules:
            raise TransactionConflict("rules.yaml changed after the transaction; refusing to overwrite it")

        agents_before = self._read_agents()
        try:
            current_block = extract_managed_block(agents_before)
        except ManagedBlockError as error:
            raise TransactionConflict(f"AGENTS.md markers are no longer valid: {error}") from error
        if current_block != target.agents_block_after:
            raise TransactionConflict("RuleGarden managed block changed after the transaction; refusing to overwrite it")
        if target.agents_block_before is None:
            raise TransactionConflict("transaction predates managed-block initialization")
        agents_after = replace_managed_block(agents_before, target.agents_block_before)

        reversal = Transaction(
            transaction_id=f"txn-{uuid4().hex}",
            operation=f"undo:{target.transaction_id}",
            rule_ids=target.rule_ids,
            before_rules=current_rules,
            after_rules=target.before_rules,
            agents_block_before=current_block,
            agents_block_after=target.agents_block_before,
        )
        try:
            self.repository.save_rules(target.before_rules)
            self._write_agents(agents_after)
            self.repository.append_history(reversal)
        except Exception as error:
            recovery_error = self._restore_after_failed_apply(current_rules, agents_before)
            detail = f"; recovery also failed: {recovery_error}" if recovery_error else ""
            raise TransactionError(f"could not undo RuleGarden transaction: {error}{detail}") from error
        return reversal

    def _find_transaction(self, history: list[Transaction], transaction_id: str | None) -> Transaction:
        if transaction_id is None:
            return history[-1]
        for transaction in reversed(history):
            if transaction.transaction_id == transaction_id:
                return transaction
        raise TransactionError(f"transaction '{transaction_id}' does not exist")

    def _restore_after_failed_apply(self, rules: RuleDocument, agents: str) -> Exception | None:
        """Best-effort compensation keeps rules consistent when a later file write fails."""
        failures: list[Exception] = []
        try:
            self.repository.save_rules(rules)
        except Exception as error:
            failures.append(error)
        try:
            # The AGENTS write is attempted even when storage recovery reports an error.
            self._write_agents(agents)
        except Exception as error:
            failures.append(error)
        return failures[0] if failures else None

    def _read_agents(self) -> str:
        return self.agents_path.read_text(encoding="utf-8") if self.agents_path.exists() else ""

    def _write_agents(self, contents: str) -> None:
        """Use the same replace-based write strategy as RuleGarden's structured state."""
        RuleRepository._atomic_write(self.agents_path, contents)
