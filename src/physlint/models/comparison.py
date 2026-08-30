"""Dataset-to-dataset regression comparison without an opaque quality score."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from physlint.models.finding import CoverageSnapshot, Finding


class RuleChange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule_id: str
    before: str
    after: str


class CoverageDelta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    episodes_before: int
    episodes_after: int
    frames_before: int | None = None
    frames_after: int | None = None
    messages_before: int | None = None
    messages_after: int | None = None
    added_streams: list[str] = Field(default_factory=list)
    removed_streams: list[str] = Field(default_factory=list)
    added_tasks: list[str] = Field(default_factory=list)
    removed_tasks: list[str] = Field(default_factory=list)
    task_count_changes: dict[str, dict[str, int]] = Field(default_factory=dict)


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["unchanged", "improved", "regressed", "changed"]
    baseline_dataset: str
    candidate_dataset: str
    baseline_fingerprint: str
    candidate_fingerprint: str
    baseline_status: str
    candidate_status: str
    new_findings: list[Finding] = Field(default_factory=list)
    resolved_findings: list[Finding] = Field(default_factory=list)
    persistent_findings: list[Finding] = Field(default_factory=list)
    rule_changes: list[RuleChange] = Field(default_factory=list)
    coverage: CoverageDelta | None = None
    baseline_coverage: CoverageSnapshot | None = None
    candidate_coverage: CoverageSnapshot | None = None
