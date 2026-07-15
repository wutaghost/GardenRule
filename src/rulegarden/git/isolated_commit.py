"""Create RuleGarden-only commits through a disposable Git index."""

from __future__ import annotations

import os
import subprocess
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from rulegarden.agents_md.managed_block import ManagedBlockError, extract_managed_block, replace_managed_block


_RULEGARDEN_PATHS = (".rulegarden/rules.yaml", ".rulegarden/config.yaml")
_AGENTS_PATH = "AGENTS.md"


@dataclass(frozen=True)
class CommitResult:
    """An explicit outcome for a commit attempt that must be safe to skip."""

    status: str
    reason: str | None = None
    commit_id: str | None = None
    changed_paths: tuple[str, ...] = ()


class IsolatedCommitManager:
    """Build an exact RuleGarden commit without staging user-owned worktree changes."""

    def __init__(self, project_root: Path) -> None:
        self.project_root = Path(project_root)

    def commit_rulegarden_changes(self, message: str) -> CommitResult:
        """Commit only rules/config plus a managed-only AGENTS.md patch, or safely skip."""
        if not self._is_git_repository():
            return CommitResult(status="skipped", reason="not_a_git_repository")
        if self._run("rev-parse", "--verify", "HEAD").returncode != 0:
            return CommitResult(status="skipped", reason="head_unavailable")
        if not message.strip():
            return CommitResult(status="skipped", reason="blank_commit_message")

        agents_result = self._prepare_agents_candidate()
        if isinstance(agents_result, CommitResult):
            return agents_result
        head_agents, candidate_agents = agents_result

        allowed_paths = [path for path in _RULEGARDEN_PATHS if (self.project_root / path).exists()]
        allowed_paths.append(_AGENTS_PATH)
        if self._has_staged_changes(allowed_paths):
            return CommitResult(status="skipped", reason="rulegarden_paths_staged")

        with self._temporary_index() as environment:
            if self._run("read-tree", "HEAD", env=environment).returncode != 0:
                return CommitResult(status="skipped", reason="temporary_index_initialization_failed")
            for path in allowed_paths:
                if path != _AGENTS_PATH:
                    result = self._run("add", "--", path, env=environment)
                    if result.returncode != 0:
                        return CommitResult(status="skipped", reason=f"could_not_stage_{path}")
            if self._stage_agents_blob(candidate_agents, environment).returncode != 0:
                return CommitResult(status="skipped", reason="could_not_stage_agents_md")

            changed_paths = tuple(
                path
                for path in self._run("diff", "--cached", "--name-only", env=environment).stdout.splitlines()
                if path
            )
            if not changed_paths:
                return CommitResult(status="skipped", reason="no_rulegarden_changes")
            if not set(changed_paths).issubset(set(allowed_paths)):
                return CommitResult(status="skipped", reason="unexpected_cached_path", changed_paths=changed_paths)
            if _AGENTS_PATH in changed_paths and not _agents_outside_block_is_unchanged(head_agents, candidate_agents):
                return CommitResult(status="skipped", reason="agents_md_outside_block_changed", changed_paths=changed_paths)

            commit = self._run("commit", "--no-verify", "-m", message.strip(), env=environment)
            if commit.returncode != 0:
                return CommitResult(status="skipped", reason="git_commit_failed", changed_paths=changed_paths)
            commit_id = self._run("rev-parse", "HEAD", env=environment).stdout.strip()

        # The disposable index updated HEAD but not the user's index. These paths were verified
        # as unstaged above, so synchronizing only them keeps status accurate without touching user work.
        if not self._sync_primary_index(changed_paths):
            return CommitResult(
                status="committed",
                reason="primary_index_sync_failed",
                commit_id=commit_id,
                changed_paths=changed_paths,
            )
        return CommitResult(status="committed", commit_id=commit_id, changed_paths=changed_paths)

    def _prepare_agents_candidate(self) -> tuple[str, str] | CommitResult:
        agents_path = self.project_root / _AGENTS_PATH
        head_agents = self._run("show", f"HEAD:{_AGENTS_PATH}")
        if head_agents.returncode != 0:
            return CommitResult(
                status="skipped",
                reason="agents_md_is_untracked" if agents_path.exists() else "agents_md_missing_from_head",
            )
        if not agents_path.exists():
            return CommitResult(status="skipped", reason="agents_md_missing_from_worktree")
        try:
            working_agents = agents_path.read_text(encoding="utf-8")
            managed_block = extract_managed_block(working_agents)
            if managed_block is None:
                return CommitResult(status="skipped", reason="agents_md_not_initialized")
            if extract_managed_block(head_agents.stdout) is None:
                return CommitResult(status="skipped", reason="agents_md_head_not_initialized")
            candidate = replace_managed_block(head_agents.stdout, managed_block)
        except (OSError, ManagedBlockError):
            return CommitResult(status="skipped", reason="agents_md_invalid")
        return head_agents.stdout, candidate

    def _is_git_repository(self) -> bool:
        result = self._run("rev-parse", "--show-toplevel")
        if result.returncode != 0:
            return False
        # A temp directory may sit below an unrelated ancestor repository. RuleGarden
        # must never treat that ancestor as the target project it is allowed to commit.
        return Path(result.stdout.strip()).resolve() == self.project_root.resolve()

    def _has_staged_changes(self, paths: list[str]) -> bool:
        return self._run("diff", "--cached", "--quiet", "--", *paths).returncode == 1

    def _stage_agents_blob(self, contents: str, environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
        blob = self._run("hash-object", "-w", "--stdin", input_text=contents)
        if blob.returncode != 0:
            return blob
        return self._run(
            "update-index",
            "--add",
            "--cacheinfo",
            f"100644,{blob.stdout.strip()},{_AGENTS_PATH}",
            env=environment,
        )

    def _sync_primary_index(self, paths: tuple[str, ...]) -> bool:
        """Move only committed RuleGarden paths in the normal index to the new HEAD blobs."""
        for path in paths:
            entry = self._run("ls-tree", "HEAD", "--", path)
            if entry.returncode != 0:
                return False
            if not entry.stdout.strip():
                result = self._run("update-index", "--force-remove", "--", path)
            else:
                metadata, _, entry_path = entry.stdout.strip().partition("\t")
                parts = metadata.split()
                if len(parts) != 3 or not entry_path:
                    return False
                mode, _, object_id = parts
                result = self._run("update-index", "--add", "--cacheinfo", f"{mode},{object_id},{entry_path}")
            if result.returncode != 0:
                return False
        return True

    @contextmanager
    def _temporary_index(self) -> Iterator[dict[str, str]]:
        descriptor, index_name = tempfile.mkstemp(prefix="rulegarden-index-", dir=self.project_root)
        os.close(descriptor)
        index_path = Path(index_name)
        index_path.unlink(missing_ok=True)
        environment = os.environ.copy()
        environment["GIT_INDEX_FILE"] = str(index_path)
        try:
            yield environment
        finally:
            index_path.unlink(missing_ok=True)
            Path(f"{index_path}.lock").unlink(missing_ok=True)

    def _run(
        self,
        *arguments: str,
        env: dict[str, str] | None = None,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *arguments],
            cwd=self.project_root,
            env=env,
            input=input_text,
            capture_output=True,
            check=False,
            text=True,
        )


def _agents_outside_block_is_unchanged(before: str, after: str) -> bool:
    """Defensively verify the AGENTS candidate differs only inside the managed markers."""
    try:
        before_block = extract_managed_block(before)
        after_block = extract_managed_block(after)
    except ManagedBlockError:
        return False
    if before_block is None or after_block is None:
        return False
    before_start = before.index(before_block)
    after_start = after.index(after_block)
    return (
        before[:before_start] == after[:after_start]
        and before[before_start + len(before_block) :] == after[after_start + len(after_block) :]
    )
