"""Machine-readable CLI envelopes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from physlint.models.finding import Report


class CliError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["error"] = "error"
    error_kind: Literal["configuration", "source", "internal", "interrupted"]
    message: str
    exit_code: int


class DemoResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["passed", "failed"]
    clean: Report
    corrupted: Report


class WriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    status: Literal["created"] = "created"
    operation: Literal["init", "baseline"]
    path: str
    suppressions: int | None = None


class DiagnosticCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    status: Literal["passed", "warning", "failed"]
    detail: str
    remediation: str | None = None


class DoctorResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1.0"] = "1.0"
    physlint_version: str
    status: Literal["passed", "failed"]
    checks: list[DiagnosticCheck] = Field(default_factory=list)
