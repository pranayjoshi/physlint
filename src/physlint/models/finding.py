"""Stable finding and report schemas."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Severity(StrEnum):
    CRITICAL = "critical"
    ERROR = "error"
    WARNING = "warning"
    NOTICE = "notice"


class RuleStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    ERRORED = "errored"


class Location(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episode: str | None = None
    stream: str | None = None
    sample_index: int | None = None
    timestamp: float | None = None
    source: str | None = None


class Finding(BaseModel):
    """Actionable evidence produced by one rule."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_version: str
    severity: Severity
    title: str
    message: str
    impact: str
    remediation: str
    observed: Any = None
    expected: Any = None
    location: Location = Field(default_factory=Location)
    evidence: dict[str, Any] = Field(default_factory=dict)
    fingerprint: str


class RuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    rule_version: str
    status: RuleStatus
    duration_ms: float
    findings: list[Finding] = Field(default_factory=list)
    reason: str | None = None
    error_kind: Literal["adapter", "rule"] | None = None


class RunSummary(BaseModel):
    passed: int = 0
    failed: int = 0
    not_run: int = 0
    errored: int = 0
    findings: int = 0


class Report(BaseModel):
    """Versioned JSON report. New fields may be added compatibly in schema 1.x."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    physlint_version: str
    adapter: str
    adapter_version: str
    dataset: str
    source_revision: str | None = None
    dataset_path: str
    source_fingerprint: str
    source_fingerprint_method: str = "metadata-and-file-stat-sha256-v1"
    configuration_digest: str
    started_at: datetime
    finished_at: datetime
    status: Literal["passed", "failed"]
    sampled: bool = False
    results: list[RuleResult]
    summary: RunSummary
