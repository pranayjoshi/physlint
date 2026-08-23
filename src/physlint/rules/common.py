"""Helpers that keep serialized findings deterministic."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import numpy as np

from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import RuleMetadata


def finding(
    metadata: RuleMetadata,
    severity: Severity,
    message: str,
    *,
    location: Location | None = None,
    observed: Any = None,
    expected: Any = None,
    evidence: dict[str, Any] | None = None,
    impact: str | None = None,
    remediation: str | None = None,
) -> Finding:
    location = location or Location()
    fingerprint_input = {
        "rule_id": metadata.id,
        "episode": location.episode,
        "stream": location.stream,
        "sample_index": location.sample_index,
        "observed": observed,
        "expected": expected,
    }
    encoded = json.dumps(fingerprint_input, sort_keys=True, separators=(",", ":"), default=_json_default)
    return Finding(
        rule_id=metadata.id,
        rule_version=metadata.version,
        severity=severity,
        title=metadata.title,
        message=message,
        impact=impact or metadata.description,
        remediation=remediation or metadata.remediation,
        observed=_json_value(observed),
        expected=_json_value(expected),
        location=location,
        evidence=_json_value(evidence or {}),
        fingerprint=hashlib.sha256(encoded.encode()).hexdigest(),
    )


def numeric_streams(dataset: Any) -> list[str]:
    ignored = {"timestamp", "frame_index", "episode_index", "index", "task_index"}
    return [
        stream.key for stream in dataset.inventory.streams if stream.kind == "numeric" and stream.key not in ignored
    ]


def _json_default(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    return json.loads(json.dumps(value, default=_json_default, allow_nan=False))
