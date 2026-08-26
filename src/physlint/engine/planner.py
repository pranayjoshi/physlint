"""Validate a quality contract and determine runnable rules."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from physlint.config import Config, ConfigurationError
from physlint.models.dataset import DatasetView
from physlint.models.finding import Severity
from physlint.models.rule import Rule
from physlint.rules import BUILTIN_RULES


@dataclass(frozen=True)
class PlannedRule:
    rule: Rule
    options: dict[str, Any]
    severity: Severity
    not_run_reason: str | None = None


def plan_rules(dataset: DatasetView, config: Config) -> list[PlannedRule]:
    registry = {rule.metadata.id: rule for rule in BUILTIN_RULES}
    unknown_rules = set(config.rules) - set(registry)
    if unknown_rules:
        raise ConfigurationError(f"unknown rule IDs: {', '.join(sorted(unknown_rules))}")
    available_streams = {stream.key for stream in dataset.inventory.streams}
    planned: list[PlannedRule] = []
    for rule in BUILTIN_RULES:
        settings = config.rules.get(rule.metadata.id)
        if settings is not None and not settings.enabled:
            continue
        configured = dict(settings.options) if settings else {}
        unknown_options = set(configured) - set(rule.metadata.option_defaults)
        if unknown_options:
            raise ConfigurationError(f"unknown options for {rule.metadata.id}: {', '.join(sorted(unknown_options))}")
        options = {**rule.metadata.option_defaults, **configured}
        if "required_streams" in options:
            options["required_streams"] = list(config.required_streams)
        _validate_options(rule.metadata.id, options)
        severity = Severity(settings.severity) if settings and settings.severity else rule.metadata.severity
        missing_capabilities = rule.metadata.required_capabilities - dataset.inventory.capabilities
        missing_streams = rule.metadata.required_streams - available_streams
        reason: str | None = None
        if missing_capabilities:
            reason = f"adapter lacks capabilities: {', '.join(sorted(missing_capabilities))}"
        elif missing_streams:
            reason = f"dataset lacks required streams: {', '.join(sorted(missing_streams))}"
        planned.append(PlannedRule(rule, options, severity, reason))
    return planned


def _validate_options(rule_id: str, options: dict[str, Any]) -> None:
    for key in ("max_findings", "stride"):
        if key in options and (not isinstance(options[key], int) or options[key] <= 0):
            raise ConfigurationError(f"{rule_id}.{key} must be a positive integer")
    for key in ("max_consecutive_frames", "frame_count_tolerance"):
        if key in options and (not isinstance(options[key], int) or options[key] < 0):
            raise ConfigurationError(f"{rule_id}.{key} must be a non-negative integer")
    for key in (
        "tolerance_fraction",
        "max_gap_multiplier",
        "max_delay_ms",
        "mean_absolute_difference",
        "max_mean_intensity",
        "max_stddev",
        "motion_delta_threshold",
        "min_motion_fraction",
    ):
        if key in options and (not isinstance(options[key], (int, float)) or float(options[key]) < 0):
            raise ConfigurationError(f"{rule_id}.{key} must be a non-negative number")
    if options.get("max_gap_ms") is not None and (
        not isinstance(options["max_gap_ms"], (int, float)) or float(options["max_gap_ms"]) < 0
    ):
        raise ConfigurationError(f"{rule_id}.max_gap_ms must be a non-negative number or null")
    if "min_motion_fraction" in options and float(options["min_motion_fraction"]) > 1:
        raise ConfigurationError(f"{rule_id}.min_motion_fraction must be at most 1")
    for key in ("required_streams", "streams", "motion_streams"):
        if key in options and (
            not isinstance(options[key], list) or not all(isinstance(value, str) for value in options[key])
        ):
            raise ConfigurationError(f"{rule_id}.{key} must be a list of stream names")
    for key in ("limits", "max_delta"):
        if key in options and not isinstance(options[key], dict):
            raise ConfigurationError(f"{rule_id}.{key} must be a mapping by stream name")
