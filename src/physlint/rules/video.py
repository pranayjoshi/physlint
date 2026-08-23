"""Selective video decode, frozen-frame, and black-frame rules."""

from __future__ import annotations

from typing import Any

import numpy as np

from physlint.models.dataset import DatasetView
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata
from physlint.rules.common import finding


def _video_streams(dataset: DatasetView) -> list[str]:
    return [stream.key for stream in dataset.inventory.streams if stream.kind == "video"]


class VideoDecodeRule:
    metadata = RuleMetadata(
        id="video.decode",
        version="1.0.0",
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
                    continue
                decoded = sum(1 for _ in dataset.iter_video_frames(episode, stream))
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
        version="1.0.0",
        title="Camera streams do not freeze",
        description="Repeated frames hide robot motion and produce misaligned visual supervision.",
        severity=Severity.ERROR,
        scope="sample",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={
            "max_consecutive_frames": 5,
            "mean_absolute_difference": 0.5,
            "stride": 1,
            "max_findings": 50,
        },
        limitations="Very static scenes can resemble a freeze; evidence points to the exact run.",
        remediation="Inspect the camera/encoder at the cited range and recollect if motion was lost.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        allowed = int(options["max_consecutive_frames"])
        threshold = float(options["mean_absolute_difference"])
        stride = int(options["stride"])
        for episode in dataset.inventory.episodes:
            for stream in _video_streams(dataset):
                if stream not in episode.video_files:
                    continue
                previous: np.ndarray | None = None
                run = 0
                run_start = 0
                last_index = 0
                for frame in dataset.iter_video_frames(episode, stream, stride=stride):
                    gray = _gray_small(frame.image)
                    if previous is not None:
                        difference = float(np.mean(np.abs(gray.astype(float) - previous.astype(float))))
                        if difference <= threshold:
                            if run == 0:
                                run_start = max(0, frame.frame_index - stride)
                            run += stride
                        else:
                            if run + 1 > allowed:
                                findings.append(
                                    _frozen_finding(
                                        self.metadata,
                                        severity,
                                        episode.identifier,
                                        stream,
                                        episode.video_files[stream],
                                        run_start,
                                        last_index,
                                        run + 1,
                                        threshold,
                                        dataset.inventory.fps,
                                    )
                                )
                            run = 0
                    previous = gray
                    last_index = frame.frame_index
                    if len(findings) >= options["max_findings"]:
                        return findings
                if run + 1 > allowed:
                    findings.append(
                        _frozen_finding(
                            self.metadata,
                            severity,
                            episode.identifier,
                            stream,
                            episode.video_files[stream],
                            run_start,
                            last_index,
                            run + 1,
                            threshold,
                            dataset.inventory.fps,
                        )
                    )
        return findings[: int(options["max_findings"])]


class BlackFramesRule:
    metadata = RuleMetadata(
        id="video.black_frames",
        version="1.0.0",
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
        for episode in dataset.inventory.episodes:
            for stream in _video_streams(dataset):
                if stream not in episode.video_files:
                    continue
                for frame in dataset.iter_video_frames(episode, stream, stride=int(options["stride"])):
                    mean = float(np.mean(frame.image))
                    stddev = float(np.std(frame.image))
                    if mean <= float(options["max_mean_intensity"]) and stddev <= float(options["max_stddev"]):
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"Black or near-empty frame at index {frame.frame_index}",
                                location=Location(
                                    episode=episode.identifier,
                                    stream=stream,
                                    sample_index=frame.frame_index,
                                    timestamp=frame.timestamp,
                                    source=episode.video_files[stream],
                                ),
                                observed={"mean_intensity": mean, "stddev": stddev},
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


def _gray_small(image: np.ndarray) -> np.ndarray:
    # Subsample rather than resize so the core rule does not require more OpenCV operations.
    gray = np.mean(image, axis=2) if image.ndim == 3 else image
    row_stride = max(1, gray.shape[0] // 64)
    col_stride = max(1, gray.shape[1] // 64)
    return gray[::row_stride, ::col_stride]


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
    fps: float,
) -> Finding:
    return finding(
        metadata,
        severity,
        f"{stream} froze for {length} consecutive frames",
        location=Location(
            episode=episode,
            stream=stream,
            sample_index=start,
            timestamp=start / fps,
            source=source,
        ),
        observed={"start_frame": start, "end_frame": end, "consecutive_frames": length},
        expected={"mean_absolute_difference_above": threshold},
    )


VIDEO_RULES: list[Rule] = [VideoDecodeRule(), FrozenFramesRule(), BlackFramesRule()]
