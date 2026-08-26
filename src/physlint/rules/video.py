"""Shared video analysis, frozen-frame, and black-frame rules."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import numpy as np

from physlint.models.dataset import DatasetView, Episode
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata
from physlint.rules.common import finding


def _video_streams(dataset: DatasetView) -> list[str]:
    return [stream.key for stream in dataset.inventory.streams if stream.kind == "video"]


class VideoDecodeRule:
    metadata = RuleMetadata(
        id="video.decode",
        version="1.1.0",
        title="Video frames decode completely",
        description="Missing or truncated camera frames remove visual observations from training.",
        severity=Severity.ERROR,
        scope="episode",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={"frame_count_tolerance": 1, "max_findings": 50},
        remediation="Recover or re-encode the source video; otherwise recollect the affected episode.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        tolerance = int(options["frame_count_tolerance"])
        for episode in dataset.inventory.episodes:
            for stream in _video_streams(dataset):
                if stream not in episode.video_files:
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"No video reference for {stream}",
                            location=Location(episode=episode.identifier, stream=stream),
                            observed="missing reference",
                            expected=episode.length,
                        )
                    )
                else:
                    decoded = dataset.video_analysis(episode, stream).decoded_frames
                    if abs(decoded - episode.length) > tolerance:
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"Decoded {decoded} of {episode.length} expected frames",
                                location=Location(
                                    episode=episode.identifier,
                                    stream=stream,
                                    source=episode.video_files[stream],
                                ),
                                observed={"decoded_frames": decoded},
                                expected={"episode_frames": episode.length, "tolerance": tolerance},
                            )
                        )
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings


class FrozenFramesRule:
    metadata = RuleMetadata(
        id="video.frozen_frames",
        version="1.1.0",
        title="Camera streams do not freeze during robot motion",
        description="Repeated frames during robot motion indicate lost or misaligned visual supervision.",
        severity=Severity.ERROR,
        scope="sample",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={
            "max_consecutive_frames": 5,
            "mean_absolute_difference": 0.5,
            "stride": 1,
            "motion_streams": ["action", "observation.state"],
            "motion_delta_threshold": 0.001,
            "min_motion_fraction": 0.25,
            "max_findings": 50,
        },
        limitations=(
            "Static scenes are ignored unless the first available configured motion stream shows motion; "
            "action is preferred over noisier observed state by default."
        ),
        remediation="Inspect the camera/encoder at the cited moving range and recollect if motion was lost.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        allowed = int(options["max_consecutive_frames"])
        threshold = float(options["mean_absolute_difference"])
        stride = int(options["stride"])
        for episode in dataset.inventory.episodes:
            motion = _episode_motion(dataset, episode, options)
            if motion is None:
                continue
            for stream in _video_streams(dataset):
                if stream not in episode.video_files:
                    continue
                analysis = dataset.video_analysis(episode, stream)
                transition_indices = np.arange(0, analysis.mean_absolute_differences.size, stride)
                frozen = analysis.mean_absolute_differences[transition_indices] <= threshold
                for run_start, run_end in _true_runs(frozen):
                    first_transition = int(transition_indices[run_start])
                    last_transition = int(transition_indices[run_end])
                    start_frame = int(analysis.frame_indices[first_transition])
                    end_frame = int(analysis.frame_indices[last_transition + 1])
                    length = end_frame - start_frame + 1
                    if length <= allowed:
                        continue
                    aligned_motion = motion[first_transition : last_transition + 1]
                    motion_fraction = float(np.mean(aligned_motion)) if aligned_motion.size else 0.0
                    if motion_fraction < float(options["min_motion_fraction"]):
                        continue
                    findings.append(
                        _frozen_finding(
                            self.metadata,
                            severity,
                            episode.identifier,
                            stream,
                            episode.video_files[stream],
                            start_frame,
                            end_frame,
                            length,
                            threshold,
                            motion_fraction,
                            dataset.inventory.fps,
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        return findings


class BlackFramesRule:
    metadata = RuleMetadata(
        id="video.black_frames",
        version="1.1.0",
        title="Camera frames contain usable signal",
        description="Black or near-empty frames remove the visual evidence expected by a policy.",
        severity=Severity.ERROR,
        scope="sample",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={
            "max_mean_intensity": 3.0,
            "max_stddev": 3.0,
            "stride": 1,
            "max_findings": 50,
        },
        remediation="Fix camera exposure or transport and recollect the affected samples.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        stride = int(options["stride"])
        for episode in dataset.inventory.episodes:
            for stream in _video_streams(dataset):
                if stream not in episode.video_files:
                    continue
                analysis = dataset.video_analysis(episode, stream)
                positions = np.arange(0, analysis.decoded_frames, stride)
                bad = (analysis.mean_intensities[positions] <= float(options["max_mean_intensity"])) & (
                    analysis.stddevs[positions] <= float(options["max_stddev"])
                )
                for run_start, run_end in _true_runs(bad):
                    selected = positions[run_start : run_end + 1]
                    start = int(analysis.frame_indices[selected[0]])
                    end = int(analysis.frame_indices[selected[-1]])
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{len(selected)} black or near-empty frame(s) from {start} to {end}",
                            location=Location(
                                episode=episode.identifier,
                                stream=stream,
                                sample_index=start,
                                timestamp=float(analysis.timestamps[selected[0]]),
                                source=episode.video_files[stream],
                            ),
                            observed={
                                "start_frame": start,
                                "end_frame": end,
                                "count": len(selected),
                                "max_mean_intensity": float(np.max(analysis.mean_intensities[selected])),
                                "max_stddev": float(np.max(analysis.stddevs[selected])),
                            },
                            expected={
                                "mean_or_stddev_above": [
                                    options["max_mean_intensity"],
                                    options["max_stddev"],
                                ]
                            },
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        return findings


def _episode_motion(dataset: DatasetView, episode: Episode, options: dict[str, Any]) -> np.ndarray | None:
    available = set(dataset.parquet_schema(episode))
    streams = tuple(stream for stream in options["motion_streams"] if stream in available)
    if not streams:
        return None
    threshold = float(options["motion_delta_threshold"])
    for stream in streams:
        chunks = [np.asarray(batch.columns[stream]) for batch in dataset.iter_batches(episode, (stream,))]
        if not chunks:
            continue
        try:
            combined = np.concatenate(chunks)
            values = np.asarray(combined, dtype=float).reshape(len(combined), -1)
        except (TypeError, ValueError):
            continue
        if len(values) < 2:
            continue
        deltas = np.max(np.abs(np.diff(values, axis=0)), axis=1)
        motion = np.zeros(max(0, episode.length - 1), dtype=bool)
        usable = min(len(motion), len(deltas))
        motion[:usable] = np.isfinite(deltas[:usable]) & (deltas[:usable] > threshold)
        return motion
    return None


def _true_runs(mask: np.ndarray) -> Iterator[tuple[int, int]]:
    indices = np.flatnonzero(mask)
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


def _frozen_finding(
    metadata: RuleMetadata,
    severity: Severity,
    episode: str,
    stream: str,
    source: str,
    start: int,
    end: int,
    length: int,
    threshold: float,
    motion_fraction: float,
    fps: float,
) -> Finding:
    return finding(
        metadata,
        severity,
        f"{stream} froze for {length} consecutive frames during robot motion",
        location=Location(
            episode=episode,
            stream=stream,
            sample_index=start,
            timestamp=start / fps,
            source=source,
        ),
        observed={
            "start_frame": start,
            "end_frame": end,
            "consecutive_frames": length,
            "motion_fraction": motion_fraction,
        },
        expected={"mean_absolute_difference_above": threshold},
    )


VIDEO_RULES: list[Rule] = [VideoDecodeRule(), FrozenFramesRule(), BlackFramesRule()]
