"""Validated, privacy-bounded data models for RuleGarden state."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _utc_now() -> datetime:
    """Create timezone-aware timestamps for durable records."""
    return datetime.now(timezone.utc)


class RuleStatus(str, Enum):
    """Lifecycle states supported by the first RuleGarden release."""

    DYNAMIC = "dynamic"
    STABLE = "stable"
    LOW_EFFECT = "low_effect"
    DISABLED = "disabled"
    DELETED = "deleted"


class Enforcement(str, Enum):
    """Advisory enforcement levels; hooks do not hard-block tool calls."""

    OBSERVE = "observe"
    WARN = "warn"
    BLOCK = "block"


class SourceType(str, Enum):
    """Origins used to explain why a rule exists."""

    LEARNED = "learned"
    MANUAL = "manual"
    BUILTIN = "builtin"


class RiskLevel(str, Enum):
    """Risk used for display ordering and advisory severity."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ScopeType(str, Enum):
    """The granularity at which a rule applies."""

    REPOSITORY = "repository"
    DIRECTORY = "directory"
    FILE = "file"


class EvidenceEventType(str, Enum):
    """Allowed evidence classes; each stores a summary rather than source text."""

    USER_CORRECTION = "user_correction"
    RULE_HIT = "rule_hit"
    RULE_VIOLATION = "rule_violation"
    ROLLBACK = "rollback"


class RuleScope(BaseModel):
    """Task metadata used by deterministic rule selection."""

    model_config = ConfigDict(extra="forbid")

    type: ScopeType = ScopeType.REPOSITORY
    paths: list[str] = Field(default_factory=list)
    task_types: list[str] = Field(default_factory=list)


class RuleEvidence(BaseModel):
    """Durable evidence references with no original conversation content."""

    model_config = ConfigDict(extra="forbid")

    summary: str = ""
    refs: list[str] = Field(default_factory=list)


class RuleMetrics(BaseModel):
    """Explainable counters that later lifecycle analysis can consume."""

    model_config = ConfigDict(extra="forbid")

    hit_count: int = Field(default=0, ge=0)
    violation_count: int = Field(default=0, ge=0)
    correction_count_before: int = Field(default=0, ge=0)
    correction_count_after: int = Field(default=0, ge=0)
    rollback_count: int = Field(default=0, ge=0)


class Rule(BaseModel):
    """A single project rule and the metadata needed to apply it safely."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    instruction: str
    status: RuleStatus = RuleStatus.DYNAMIC
    enabled: bool = True
    source_type: SourceType = SourceType.LEARNED
    enforcement: Enforcement = Enforcement.WARN
    risk_level: RiskLevel = RiskLevel.MEDIUM
    scope: RuleScope = Field(default_factory=RuleScope)
    exceptions: list[str] = Field(default_factory=list)
    evidence: RuleEvidence = Field(default_factory=RuleEvidence)
    metrics: RuleMetrics = Field(default_factory=RuleMetrics)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)
    last_hit_at: datetime | None = None
    previous_status: RuleStatus | None = None

    @field_validator("instruction")
    @classmethod
    def require_instruction(cls, value: str) -> str:
        """Normalize instructions while rejecting invisible long-lived rules."""
        normalized = value.strip()
        if not normalized:
            raise ValueError("instruction must not be blank")
        return normalized


class RuleDocument(BaseModel):
    """The complete contents of `.rulegarden/rules.yaml`."""

    model_config = ConfigDict(extra="forbid")

    version: int = Field(default=1, ge=1)
    rules: list[Rule] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_unique_rule_ids(self) -> "RuleDocument":
        """Prevent ambiguous updates and transaction restoration."""
        identifiers = [rule.id for rule in self.rules]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("rule ids must be unique")
        return self


class EvidenceEvent(BaseModel):
    """An append-only, redacted explanation of a rule-related event."""

    model_config = ConfigDict(extra="forbid")

    event_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    rule_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    type: EvidenceEventType
    summary: str = Field(min_length=1)
    paths: list[str] = Field(default_factory=list)
    diff_summary: str | None = None
    task_id: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)

    @model_validator(mode="before")
    @classmethod
    def reject_sensitive_payloads(cls, data: Any) -> Any:
        """Reject raw-prompt and credential fields before evidence is persisted."""
        if isinstance(data, dict):
            prohibited = {"prompt", "transcript", "secret", "token", "api_key"}
            found = prohibited.intersection(key.lower() for key in data)
            if found:
                raise ValueError(f"evidence cannot contain sensitive fields: {sorted(found)}")
        return data


class TaskState(BaseModel):
    """Ephemeral task metadata retained only under `.rulegarden/runtime/`."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    task_summary: str = Field(min_length=1)
    task_types: list[str] = Field(default_factory=list)
    expected_paths: list[str] = Field(default_factory=list)
    risk_signals: list[str] = Field(default_factory=list)
    selected_rule_ids: list[str] = Field(default_factory=list)
    touched_paths: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=_utc_now)


class Transaction(BaseModel):
    """A reversible record of RuleGarden-owned state changes."""

    model_config = ConfigDict(extra="forbid")

    transaction_id: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,63}$")
    operation: str = Field(min_length=1)
    rule_ids: list[str] = Field(default_factory=list)
    before_rules: RuleDocument
    after_rules: RuleDocument
    agents_block_before: str | None = None
    agents_block_after: str | None = None
    commit_status: str | None = None
    created_at: datetime = Field(default_factory=_utc_now)
