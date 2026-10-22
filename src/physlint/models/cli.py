"""Machine-readable CLI envelopes."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

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
