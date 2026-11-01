"""Timestamp, sampling, gap, overlap, and delay rules."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np

from physlint.models.dataset import DatasetView, Episode, SampleBatch
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata, RuleNotApplicable
from physlint.rules.common import finding


def _timestamp_batches(dataset: DatasetView, episode: Episode) -> Iterator[SampleBatch]:
    if "timestamp" not in dataset.parquet_schema(episode):
        return iter(())
    return dataset.iter_batches(episode, ("timestamp",))


def _fps(dataset: DatasetView) -> float:
    if dataset.inventory.fps is None or dataset.inventory.fps <= 0:
        raise RuleNotApplicable("source does not declare a positive FPS")
    return dataset.inventory.fps


class MonotonicTimestampsRule:
    metadata = RuleMetadata(
        id="temporal.monotonic",
        version="1.1.0",
        title="Timestamps are strictly monotonic",
        description="Non-finite, reordered, or repeated timestamps break sequence order and synchronization.",
        severity=Severity.ERROR,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"timestamps", "episodes"}),
        option_defaults={"max_findings": 50},
        remediation="Repair collection clock ordering or recollect the affected episode.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        for episode in dataset.inventory.episodes:
            previous: float | None = None
            sample_index = 0
            for batch in _timestamp_batches(dataset, episode):
                values = np.asarray(batch.columns["timestamp"], dtype=float).reshape(-1)
                if values.size == 0:
                    continue
                for index in np.flatnonzero(~np.isfinite(values)):
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"Timestamp is not finite at sample {sample_index + int(index)}",
                            location=Location(
                                episode=episode.identifier,
                                stream="timestamp",
                                sample_index=sample_index + int(index),
                                source=episode.data_file,
                            ),
                            observed=str(values[index]),
                            expected="finite timestamp in seconds",
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
                positions = np.flatnonzero(np.isfinite(values))
                if positions.size == 0:
                    sample_index += len(values)
                    continue
                finite = values[positions]
                diffs = np.diff(finite, prepend=previous if previous is not None else finite[0] - 1)
                for offset in np.flatnonzero(diffs <= 0):
                    if previous is None and offset == 0:
                        continue
                    index = positions[offset]
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"Timestamp did not increase at sample {sample_index + int(index)}",
                            location=Location(
                                episode=episode.identifier,
                                stream="timestamp",
                                sample_index=sample_index + int(index),
                                timestamp=float(values[index]),
                                source=episode.data_file,
                            ),
                            observed=float(diffs[offset]),
                            expected="delta > 0 seconds",
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
                previous = float(finite[-1])
                sample_index += len(values)
        return findings


class SamplingIntervalRule:
    metadata = RuleMetadata(
        id="temporal.sampling_interval",
        version="1.0.0",
        title="Sampling interval matches declared FPS",
        description="Unstable sample cadence changes the physical meaning of actions and velocities.",
        severity=Severity.WARNING,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"timestamps", "episodes"}),
        option_defaults={"tolerance_fraction": 0.2, "max_findings": 50},
        remediation="Check recorder scheduling and clock sources; recollect unstable episodes.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        expected = 1.0 / _fps(dataset)
        tolerance = expected * float(options["tolerance_fraction"])
        findings = []
        for episode in dataset.inventory.episodes:
            previous: float | None = None
            offset = 0
            for batch in _timestamp_batches(dataset, episode):
                values = np.asarray(batch.columns["timestamp"], dtype=float).reshape(-1)
                combined = values if previous is None else np.concatenate(([previous], values))
                diffs = np.diff(combined)
                bad = np.flatnonzero(np.isfinite(diffs) & (diffs > 0) & (np.abs(diffs - expected) > tolerance))
                for index in bad:
                    sample = offset + int(index) + (1 if previous is None else 0)
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"Unexpected sampling interval in {episode.identifier}",
                            location=Location(
                                episode=episode.identifier,
                                stream="timestamp",
                                sample_index=sample,
                                timestamp=float(combined[index + 1]),
                            ),
                            observed={"interval_ms": float(diffs[index] * 1000)},
                            expected={
                                "interval_ms": expected * 1000,
                                "tolerance_ms": tolerance * 1000,
                            },
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
                if values.size:
                    previous = float(values[-1])
                offset += len(values)
        return findings


class MaxGapRule:
    metadata = RuleMetadata(
        id="temporal.max_gap",
        version="1.1.0",
        title="Timestamp gaps stay below the limit",
        description="Large gaps indicate dropped samples or a stalled collection process.",
        severity=Severity.ERROR,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"timestamps", "episodes"}),
        option_defaults={"max_gap_ms": None, "max_gap_multiplier": 2.0, "max_findings": 50},
        remediation="Inspect transport/recorder drops and recollect the affected time range.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        configured_limit = options["max_gap_ms"]
        limit_ms = (
            float(configured_limit)
            if configured_limit is not None
            else (1000.0 / _fps(dataset)) * float(options["max_gap_multiplier"])
        )
        limit = limit_ms / 1000.0
        findings = []
        for episode in dataset.inventory.episodes:
            chunks = [
                np.asarray(batch.columns["timestamp"], dtype=float).reshape(-1)
                for batch in _timestamp_batches(dataset, episode)
            ]
            values = np.concatenate(chunks) if chunks else np.asarray([], dtype=float)
            diffs = np.diff(values)
            for start, end in _contiguous_runs(np.flatnonzero(np.isfinite(diffs) & (diffs > limit))):
                run = diffs[start : end + 1]
                max_gap_ms = float(np.max(run) * 1000)
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"{len(run)} timestamp gap(s) exceed {limit_ms:.1f} ms",
                        location=Location(
                            episode=episode.identifier,
                            stream="timestamp",
                            sample_index=start + 1,
                            timestamp=float(values[start + 1]),
                        ),
                        observed={
                            "count": len(run),
                            "start_sample": start + 1,
                            "end_sample": end + 1,
                            "max_gap_ms": max_gap_ms,
                        },
                        expected={
                            "max_gap_ms": limit_ms,
                            "basis": "configured" if configured_limit is not None else "declared_fps",
                        },
                    )
                )
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings


class StreamOverlapRule:
    metadata = RuleMetadata(
        id="temporal.stream_overlap",
        version="1.0.0",
        title="Required streams cover complete episodes",
        description="Missing values leave observations and actions without aligned counterparts.",
        severity=Severity.ERROR,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"episodes"}),
        option_defaults={
            "required_streams": ["observation.state", "action"],
            "max_findings": 50,
        },
        remediation="Recover dropped stream values or exclude and recollect incomplete episodes.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        required = tuple(options["required_streams"])
        for episode in dataset.inventory.episodes:
            available = set(dataset.parquet_schema(episode))
            selected = tuple(stream for stream in required if stream in available)
            if not selected:
                continue
            offset = 0
            for batch in dataset.iter_batches(episode, selected):
                for stream in selected:
                    missing = _missing_rows(batch.columns[stream])
                    for index in np.flatnonzero(missing):
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"{stream} is missing at an episode sample",
                                location=Location(
                                    episode=episode.identifier,
                                    stream=stream,
                                    sample_index=offset + int(index),
                                ),
                                observed="null or empty",
                                expected="value present for every episode sample",
                            )
                        )
                        if len(findings) >= options["max_findings"]:
                            return findings
                offset += len(next(iter(batch.columns.values())))
        return findings


class ObservationActionDelayRule:
    metadata = RuleMetadata(
        id="temporal.observation_action_delay",
        version="1.0.0",
        title="Observation/action delay stays within the limit",
        description="Excess or inconsistent control delay teaches policies from misaligned causes and effects.",
        severity=Severity.ERROR,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"stream_timestamps", "episodes"}),
        required_streams=frozenset({"observation.timestamp", "action.timestamp"}),
        option_defaults={"max_delay_ms": 100.0, "max_findings": 50},
        limitations="Runs only when independent observation and action timestamp columns exist.",
        remediation="Synchronize recorder clocks and fix transport buffering before recollection.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        limit = float(options["max_delay_ms"]) / 1000.0
        findings = []
        columns = ("observation.timestamp", "action.timestamp")
        for episode in dataset.inventory.episodes:
            offset = 0
            for batch in dataset.iter_batches(episode, columns):
                observation = np.asarray(batch.columns[columns[0]], dtype=float).reshape(-1)
                action = np.asarray(batch.columns[columns[1]], dtype=float).reshape(-1)
                delay = action - observation
                for index in np.flatnonzero(np.abs(delay) > limit):
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"Observation/action delay is {delay[index] * 1000:.1f} ms",
                            location=Location(
                                episode=episode.identifier,
                                stream="action",
                                sample_index=offset + int(index),
                                timestamp=float(action[index]),
                            ),
                            observed={"delay_ms": float(delay[index] * 1000)},
                            expected={"absolute_max_delay_ms": options["max_delay_ms"]},
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
                offset += len(delay)
        return findings


class EpisodeStartRule:
    metadata = RuleMetadata(
        id="temporal.episode_start",
        version="1.0.0",
        title="Episodes start at the dataset's usual time",
        description="An offset episode clock makes timestamp-based video lookups return the wrong frames.",
        severity=Severity.ERROR,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"timestamps", "episodes"}),
        option_defaults={"max_findings": 50},
        limitations="Compares each episode with the dataset median, so a shift shared by every episode passes.",
        remediation="Rebase the episode's timestamps to the dataset convention.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        interval = 1.0 / _fps(dataset)
        starts = {
            episode.identifier: values[0]
            for episode, values in _episode_timestamps(dataset)
            if values.size and np.isfinite(values[0])
        }
        if not starts:
            return []
        reference = float(np.median(list(starts.values())))
        findings = [
            finding(
                self.metadata,
                severity,
                f"{identifier} starts {start - reference:.3f} s from the dataset's usual time",
                location=Location(episode=identifier, stream="timestamp", sample_index=0),
                observed=float(start),
                expected={"start_seconds": reference, "tolerance_seconds": interval},
            )
            for identifier, start in starts.items()
            if abs(start - reference) > interval
        ]
        return findings[: int(options["max_findings"])]


class ClockDriftRule:
    metadata = RuleMetadata(
        id="temporal.clock_drift",
        version="1.0.0",
        title="Episode duration matches sample count and FPS",
        description="A clock running fast or slow silently desynchronizes samples from video.",
        severity=Severity.ERROR,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"timestamps", "episodes"}),
        option_defaults={"max_drift_frames": 1.0, "max_findings": 50},
        remediation="Correct the episode clock or the declared FPS, then re-export.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        interval = 1.0 / _fps(dataset)
        limit = interval * float(options["max_drift_frames"])
        findings = []
        for episode, values in _episode_timestamps(dataset):
            finite = values[np.isfinite(values)]
            if finite.size != values.size or values.size < 2:
                continue
            duration = float(values[-1] - values[0])
            expected = (values.size - 1) * interval
            if abs(duration - expected) > limit:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"{episode.identifier} lasts {duration:.3f} s; {values.size} samples imply {expected:.3f} s",
                        location=Location(episode=episode.identifier, stream="timestamp"),
                        observed={"duration_seconds": duration},
                        expected={"duration_seconds": expected, "tolerance_seconds": limit},
                    )
                )
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings


def _episode_timestamps(dataset: DatasetView) -> Iterator[tuple[Episode, np.ndarray]]:
    for episode in dataset.inventory.episodes:
        chunks = [
            np.asarray(batch.columns["timestamp"], dtype=float).reshape(-1)
            for batch in _timestamp_batches(dataset, episode)
        ]
        yield episode, np.concatenate(chunks) if chunks else np.asarray([], dtype=float)


def _missing_rows(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values)
    if array.dtype == object:
        return np.asarray([value is None or (hasattr(value, "__len__") and len(value) == 0) for value in array])
    return np.zeros(array.shape[0], dtype=bool)


def _contiguous_runs(indices: np.ndarray) -> Iterator[tuple[int, int]]:
    if indices.size == 0:
        return
    start = previous = int(indices[0])
    for raw in indices[1:]:
        current = int(raw)
        if current != previous + 1:
            yield start, previous
            start = current
        previous = current
    yield start, previous


TEMPORAL_RULES: list[Rule] = [
    MonotonicTimestampsRule(),
    SamplingIntervalRule(),
    MaxGapRule(),
    StreamOverlapRule(),
    ObservationActionDelayRule(),
    EpisodeStartRule(),
    ClockDriftRule(),
]
