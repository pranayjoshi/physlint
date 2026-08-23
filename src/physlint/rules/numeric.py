"""Finite-value, configured-bound, and motion-discontinuity checks."""

from __future__ import annotations

from typing import Any

import numpy as np

from physlint.models.dataset import DatasetView
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata, RuleNotApplicable
from physlint.rules.common import finding, numeric_streams


class FiniteValuesRule:
    metadata = RuleMetadata(
        id="numeric.finite_values",
        version="1.0.0",
        title="Numeric values are finite",
        description="NaN and infinite observations or actions poison losses and model parameters.",
        severity=Severity.ERROR,
        scope="sample",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"streams": [], "max_findings": 50},
        remediation="Remove or recollect affected samples and fix the producing sensor or transform.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        requested = list(options["streams"]) or numeric_streams(dataset)
        findings = []
        for episode in dataset.inventory.episodes:
            available = set(dataset.parquet_schema(episode))
            for stream in requested:
                if stream not in available:
                    continue
                offset = 0
                for batch in dataset.iter_batches(episode, (stream,)):
                    try:
                        values = np.asarray(batch.columns[stream], dtype=float)
                    except (TypeError, ValueError):
                        continue
                    flat = values.reshape(len(values), -1)
                    bad_rows = np.flatnonzero(~np.all(np.isfinite(flat), axis=1))
                    for row in bad_rows:
                        bad_dimensions = np.flatnonzero(~np.isfinite(flat[row])).tolist()
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"Non-finite value in {stream}",
                                location=Location(
                                    episode=episode.identifier,
                                    stream=stream,
                                    sample_index=offset + int(row),
                                ),
                                observed={"non_finite_dimensions": bad_dimensions},
                                expected="all values finite",
                            )
                        )
                        if len(findings) >= options["max_findings"]:
                            return findings
                    offset += len(values)
        return findings


class NumericBoundsRule:
    metadata = RuleMetadata(
        id="numeric.configured_bounds",
        version="1.0.0",
        title="Numeric values respect configured limits",
        description="Out-of-limit state, action, velocity, or force values may be corrupt or unsafe.",
        severity=Severity.ERROR,
        scope="sample",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"limits": {}, "max_findings": 50},
        limitations="Requires robot- or task-specific min/max limits in configuration.",
        remediation="Verify units and calibration; exclude or recollect values outside physical limits.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        limits = options["limits"]
        if not limits:
            raise RuleNotApplicable("no numeric limits configured")
        findings = []
        for episode in dataset.inventory.episodes:
            available = set(dataset.parquet_schema(episode))
            for stream, contract in limits.items():
                if stream not in available:
                    continue
                lower = np.asarray(contract.get("min", -np.inf), dtype=float)
                upper = np.asarray(contract.get("max", np.inf), dtype=float)
                offset = 0
                for batch in dataset.iter_batches(episode, (stream,)):
                    values = np.asarray(batch.columns[stream], dtype=float)
                    flat = values.reshape(len(values), -1)
                    try:
                        bad = (flat < lower) | (flat > upper)
                    except ValueError as exc:
                        raise ValueError(f"limits for {stream} do not match its shape") from exc
                    for row in np.flatnonzero(np.any(bad, axis=1)):
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"{stream} exceeds configured limits",
                                location=Location(
                                    episode=episode.identifier,
                                    stream=stream,
                                    sample_index=offset + int(row),
                                ),
                                observed=flat[row].tolist(),
                                expected={"min": lower.tolist(), "max": upper.tolist()},
                            )
                        )
                        if len(findings) >= options["max_findings"]:
                            return findings
                    offset += len(values)
        return findings


class DiscontinuityRule:
    metadata = RuleMetadata(
        id="numeric.discontinuity",
        version="1.0.0",
        title="Numeric motion has no implausible discontinuities",
        description="Large one-sample jumps indicate encoder resets, unit changes, or corrupt motion.",
        severity=Severity.ERROR,
        scope="sample",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"max_delta": {}, "max_findings": 50},
        limitations="Requires per-stream maximum absolute sample deltas in configuration.",
        remediation="Check encoder resets and units; recollect or split the affected recording.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        contracts = options["max_delta"]
        if not contracts:
            raise RuleNotApplicable("no discontinuity thresholds configured")
        findings = []
        for episode in dataset.inventory.episodes:
            available = set(dataset.parquet_schema(episode))
            for stream, threshold in contracts.items():
                if stream not in available:
                    continue
                limit = np.asarray(threshold, dtype=float)
                previous: np.ndarray | None = None
                offset = 0
                for batch in dataset.iter_batches(episode, (stream,)):
                    values = np.asarray(batch.columns[stream], dtype=float).reshape(len(batch.columns[stream]), -1)
                    combined = values if previous is None else np.vstack((previous, values))
                    deltas = np.abs(np.diff(combined, axis=0))
                    try:
                        bad = deltas > limit
                    except ValueError as exc:
                        raise ValueError(f"max_delta for {stream} does not match its shape") from exc
                    for row in np.flatnonzero(np.any(bad, axis=1)):
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"Implausible one-sample jump in {stream}",
                                location=Location(
                                    episode=episode.identifier,
                                    stream=stream,
                                    sample_index=offset + int(row) + 1,
                                ),
                                observed={"absolute_delta": deltas[row].tolist()},
                                expected={"max_delta": limit.tolist()},
                            )
                        )
                        if len(findings) >= options["max_findings"]:
                            return findings
                    if len(values):
                        previous = values[-1]
                    offset += len(values)
        return findings


NUMERIC_RULES: list[Rule] = [FiniteValuesRule(), NumericBoundsRule(), DiscontinuityRule()]
