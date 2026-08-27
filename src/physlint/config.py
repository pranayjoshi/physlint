"""Strict project configuration and quality-contract loading."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class RuleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    severity: Literal["critical", "error", "warning", "notice"] | None = None
    options: dict[str, Any] = Field(default_factory=dict)


class ReportSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    json_enabled: bool = Field(default=True, alias="json")
    output_dir: str = ".physlint/reports"


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    config_version: Literal[1] = 1
    adapter: Literal["auto", "lerobot", "mcap"] = "auto"
    profile: Literal["auto", "generic", "ros2"] = "auto"
    required_streams: list[str] = Field(default_factory=lambda: ["observation.state", "action"])
    fail_on: Literal["critical", "error", "warning", "notice"] = "error"
    rules: dict[str, RuleSettings] = Field(default_factory=dict)
    reports: ReportSettings = Field(default_factory=ReportSettings)

    @field_validator("required_streams")
    @classmethod
    def unique_streams(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            raise ValueError("required_streams must not contain duplicates")
        return value

    def digest(self) -> str:
        data = json.dumps(self.model_dump(mode="json", by_alias=True), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(data.encode()).hexdigest()


class ConfigurationError(ValueError):
    """Invalid or unreadable user configuration."""


def load_config(path: Path | None, dataset_path: Path | None = None) -> Config:
    candidate = path
    if candidate is None and dataset_path is not None:
        base = dataset_path if dataset_path.is_dir() else dataset_path.parent
        local = base / "physlint.yaml"
        cwd = Path.cwd() / "physlint.yaml"
        candidate = local if local.is_file() else cwd if cwd.is_file() else None
    if candidate is None:
        return Config()
    try:
        payload = yaml.safe_load(candidate.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ConfigurationError("configuration root must be a mapping")
        return Config.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigurationError(f"invalid configuration {candidate}: {exc}") from exc


DEFAULT_CONFIG = """# Physlint quality contract
config_version: 1
adapter: auto
profile: auto
required_streams:
  - observation.state
  - action
fail_on: error
rules:
  temporal.max_gap:
    options:
      max_gap_multiplier: 2.0
  video.frozen_frames:
    options:
      max_consecutive_frames: 5
reports:
  json: true
  output_dir: .physlint/reports
"""
