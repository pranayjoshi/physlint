"""Reviewed exception baselines. Suppressions never hide new fingerprints."""

from __future__ import annotations

import hashlib
import json
from datetime import date

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Suppression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fingerprint: str
    rule_id: str
    reason: str
    author: str
    accepted_at: date
    expires_at: date | None = None

    @field_validator("fingerprint", "rule_id", "reason", "author")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()


class Baseline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_version: int = 1
    created_at: date
    author: str
    dataset: str | None = None
    source_fingerprint: str | None = None
    reason: str
    suppressions: list[Suppression] = Field(default_factory=list)

    @field_validator("author", "reason")
    @classmethod
    def required_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must be a non-empty string")
        return value.strip()

    def digest(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode()).hexdigest()
