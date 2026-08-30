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
    cached: bool = False


class CoverageSnapshot(BaseModel):
    """Distributions present in a source. This is not a quality score."""

    model_config = ConfigDict(extra="forbid")

    episodes: int = 0
    frames: int | None = None
    messages: int | None = None
    streams: list[str] = Field(default_factory=list)
    tasks: dict[str, int] = Field(default_factory=dict)
    length_min: int | None = None
    length_max: int | None = None
    robot_type: str | None = None
    fps: float | None = None


class CacheSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    used: bool = False
    hits: int = 0
    misses: int = 0
    directory: str | None = None


class AppliedSuppression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    rule_id: str
    reason: str
    author: str
    accepted_at: str
    expires_at: str | None = None


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
    coverage: CoverageSnapshot | None = None
    cache: CacheSummary = Field(default_factory=CacheSummary)
    suppressed: list[AppliedSuppression] = Field(default_factory=list)
    plugins: list[str] = Field(default_factory=list)
