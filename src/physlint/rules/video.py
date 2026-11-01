"""Shared video analysis, frozen-frame, and black-frame rules."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import numpy as np

from physlint.models.dataset import DatasetView, Episode, VideoProbe
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata, RuleNotApplicable
from physlint.rules.common import finding

NOISE_FACTOR = 6.0


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
        version="2.0.0",
        title="Camera streams do not freeze during robot motion",
        description="Repeated frames during robot motion indicate lost or misaligned visual supervision.",
        severity=Severity.WARNING,
        scope="sample",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={
            "max_consecutive_frames": 5,
            "max_cell_difference": 2.0,
            "stride": 1,
            "motion_streams": ["action", "observation.state"],
            "motion_delta_threshold": 0.001,
            "min_run_displacement": 0.05,
            "max_findings": 50,
        },
        limitations=(
            "A frame counts as repeated only if no cell of a small averaged grid changes. A run counts only if "
            "every available motion stream moved during it, above its own noise and by min_run_displacement of "
            "its range in the episode, so slow starts and stationary robots are not reported."
        ),
        remediation="Inspect the camera/encoder at the cited moving range and recollect if motion was lost.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        allowed = int(options["max_consecutive_frames"])
        threshold = float(options["max_cell_difference"])
        stride = int(options["stride"])
        for episode in dataset.inventory.episodes:
            profiles = _motion_profiles(dataset, episode, options)
            if not profiles:
                continue
            for stream in _video_streams(dataset):
                if stream not in episode.video_files:
                    continue
                analysis = dataset.video_analysis(episode, stream)
                transition_indices = np.arange(0, analysis.max_cell_differences.size, stride)
                frozen = analysis.max_cell_differences[transition_indices] <= threshold
                for run_start, run_end in _true_runs(frozen):
                    first_transition = int(transition_indices[run_start])
                    last_transition = int(transition_indices[run_end])
                    start_frame = int(analysis.frame_indices[first_transition])
                    end_frame = int(analysis.frame_indices[last_transition + 1])
                    length = end_frame - start_frame + 1
                    if length <= allowed:
                        continue
                    displacement = min(
                        profile.displacement(first_transition, last_transition + 1) for profile in profiles
                    )
                    if displacement < float(options["min_run_displacement"]):
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
                            displacement,
                            dataset.inventory.fps or 1.0,
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        return findings


class RepeatedFramesRule:
    metadata = RuleMetadata(
        id="video.repeated_frames",
        version="1.0.0",
        title="Cameras deliver new frames at the declared rate",
        description="A camera repeating frames during motion delivers less visual information than FPS implies.",
        severity=Severity.WARNING,
        scope="episode",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={
            "max_cell_difference": 2.0,
            "min_repeat_fraction": 0.35,
            "min_changed_ratio": 3.0,
            "min_moving_transitions": 20,
            "motion_streams": ["action", "observation.state"],
            "motion_delta_threshold": 0.001,
            "max_findings": 50,
        },
        limitations="Runs only on transitions where every available motion stream shows sustained motion.",
        remediation="Check camera frame rate and driver buffering, or declare the true FPS.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        threshold = float(options["max_cell_difference"])
        for episode in dataset.inventory.episodes:
            motion = _episode_motion(dataset, episode, options)
            if motion is None:
                continue
            for stream in _video_streams(dataset):
                if stream not in episode.video_files:
                    continue
                changes = dataset.video_analysis(episode, stream).max_cell_differences
                usable = min(changes.size, motion.size)
                moving = changes[:usable][motion[:usable]]
                if moving.size < int(options["min_moving_transitions"]):
                    continue
                repeated = moving <= threshold
                fresh = moving[~repeated]
                fraction = float(np.mean(repeated))
                if fraction < float(options["min_repeat_fraction"]) or fresh.size == 0:
                    continue
                if float(np.median(fresh)) < threshold * float(options["min_changed_ratio"]):
                    continue
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"{stream} repeated {fraction:.0%} of frames during robot motion",
                        location=Location(
                            episode=episode.identifier, stream=stream, source=episode.video_files[stream]
                        ),
                        observed={"repeat_fraction": fraction, "moving_transitions": int(moving.size)},
                        expected={"repeat_fraction_below": options["min_repeat_fraction"]},
                    )
                )
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings


class BlackFramesRule:
    metadata = RuleMetadata(
        id="video.black_frames",
        version="1.2.0",
        title="Camera frames contain usable signal",
        description="Black, saturated, or near-empty frames remove the visual evidence expected by a policy.",
        severity=Severity.ERROR,
        scope="sample",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={
            "max_mean_intensity": 3.0,
            "min_saturated_intensity": 252.0,
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
                means = analysis.mean_intensities[positions]
                extreme = (means <= float(options["max_mean_intensity"])) | (
                    means >= float(options["min_saturated_intensity"])
                )
                bad = extreme & (analysis.stddevs[positions] <= float(options["max_stddev"]))
                for run_start, run_end in _true_runs(bad):
                    selected = positions[run_start : run_end + 1]
                    start = int(analysis.frame_indices[selected[0]])
                    end = int(analysis.frame_indices[selected[-1]])
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{len(selected)} black, saturated, or near-empty frame(s) from {start} to {end}",
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


@dataclass(frozen=True)
class _MotionProfile:
    """One stream's smoothed values with the scales needed to judge a displacement."""

    values: np.ndarray
    smoothed: np.ndarray
    noise: np.ndarray
    scale: np.ndarray
    floor: float

    def displacement(self, start: int, end: int) -> float:
        """Return the root-mean-square move across dimensions as a fraction of range, ignoring noise-level moves."""
        last = min(end, self.smoothed.shape[0] - 1)
        first = min(start, last)
        moved = np.abs(self.smoothed[last] - self.smoothed[first])
        meaningful = moved > np.maximum(self.noise * NOISE_FACTOR, self.floor)
        if not np.any(meaningful):
            return 0.0
        relative = np.where(meaningful, moved / self.scale, 0.0)
        return float(np.sqrt(np.mean(relative**2)))


def _motion_profiles(dataset: DatasetView, episode: Episode, options: dict[str, Any]) -> list[_MotionProfile]:
    profiles = []
    for values in _motion_values(dataset, episode, options):
        clean = np.where(np.isfinite(values), values, 0.0)
        profiles.append(
            _MotionProfile(
                values=clean,
                smoothed=_smoothed(clean),
                noise=_sample_noise(clean),
                scale=np.maximum(np.ptp(clean, axis=0), 1e-9),
                floor=float(options["motion_delta_threshold"]),
            )
        )
    return profiles


def _motion_values(dataset: DatasetView, episode: Episode, options: dict[str, Any]) -> Iterator[np.ndarray]:
    available = set(dataset.parquet_schema(episode))
    for stream in options["motion_streams"]:
        if stream not in available:
            continue
        chunks = [np.asarray(batch.columns[stream]) for batch in dataset.iter_batches(episode, (stream,))]
        if not chunks:
            continue
        try:
            joined = np.concatenate(chunks)
            values = np.asarray(joined, dtype=float).reshape(len(joined), -1)
        except (TypeError, ValueError):
            continue
        if len(values) >= 2:
            yield values


def _smoothed(values: np.ndarray) -> np.ndarray:
    """Moving average with edge padding, so episode ends do not look like motion toward zero."""
    kernel = min(5, values.shape[0])
    padded = np.pad(values, ((kernel // 2, kernel - 1 - kernel // 2), (0, 0)), mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, kernel, axis=0)
    return np.asarray(windows.mean(axis=-1), dtype=float)


def _sample_noise(values: np.ndarray) -> np.ndarray:
    """Estimate white sample noise from second differences, which smooth motion barely affects."""
    if values.shape[0] < 3:
        return np.zeros(values.shape[1])
    return np.asarray(1.4826 * np.median(np.abs(np.diff(values, n=2, axis=0)), axis=0) / np.sqrt(6.0), dtype=float)


def _episode_motion(dataset: DatasetView, episode: Episode, options: dict[str, Any]) -> np.ndarray | None:
    """Mark transitions where every available motion stream shows sustained motion."""
    combined: np.ndarray | None = None
    for values in _motion_values(dataset, episode, options):
        moving = np.zeros(max(0, episode.length - 1), dtype=bool)
        sustained = _sustained_motion(values, float(options["motion_delta_threshold"]))
        usable = min(moving.size, sustained.size)
        moving[:usable] = sustained[:usable]
        combined = moving if combined is None else combined & moving
    return combined


def _sustained_motion(values: np.ndarray, floor: float, window: int = 10) -> np.ndarray:
    """Compare smoothed displacement with each dimension's own sample noise, so jitter is not motion."""
    samples = values.shape[0]
    clean = np.where(np.isfinite(values), values, 0.0)
    smoothed = _smoothed(clean)
    reach = max(1, min(window, samples - 1))
    displacement = np.abs(smoothed[reach:] - smoothed[:-reach])
    above = np.any(displacement > np.maximum(_sample_noise(clean) * NOISE_FACTOR, floor), axis=1)
    mask = np.zeros(samples - 1, dtype=bool)
    for start in np.flatnonzero(above):
        mask[start : start + reach] = True
    return mask


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
    displacement: float,
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
            "run_displacement": displacement,
        },
        expected={"max_cell_difference_above": threshold},
    )


class BitstreamRule:
    metadata = RuleMetadata(
        id="video.bitstream",
        version="1.0.0",
        title="Video bitstreams decode without errors",
        description="Decoders conceal corruption by painting over it, so a frame count alone can hide damaged frames.",
        severity=Severity.ERROR,
        scope="episode",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={"max_findings": 50},
        limitations="Requires PyAV, installed by the 'video' extra.",
        remediation="Restore the video from its source or recollect the affected episodes.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        for stream, relative, episodes in _video_files(dataset):
            probe = _probe(dataset, relative)
            if not probe.decode_errors:
                continue
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    f"{probe.decode_errors} decode error(s) in {relative}",
                    location=Location(
                        episode=_episode_at(episodes, stream, probe.first_error_time),
                        stream=stream,
                        timestamp=probe.first_error_time,
                        source=relative,
                    ),
                    observed={"decode_errors": probe.decode_errors},
                    expected="no decode errors",
                )
            )
            if len(findings) >= options["max_findings"]:
                break
        return findings


class VideoTimelineRule:
    metadata = RuleMetadata(
        id="video.timeline",
        version="1.0.0",
        title="Episode video ranges match stored frame times",
        description="Ranges that disagree with stored frame times make video lookups return the wrong frames.",
        severity=Severity.ERROR,
        scope="episode",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={"tolerance_frames": 0.5, "max_findings": 50},
        limitations="Requires PyAV, installed by the 'video' extra. Whole-frame shifts need a neighboring range.",
        remediation="Rebuild episode video ranges from the stored frame times, or re-export the video.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        fps = float(dataset.inventory.fps or 0.0)
        if fps <= 0:
            raise RuleNotApplicable("source does not declare a positive FPS")
        interval = 1.0 / fps
        tolerance = interval * float(options["tolerance_frames"])

        def add(message: str, episode: str | None, stream: str, source: str, observed: Any, expected: Any) -> None:
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    message,
                    location=Location(episode=episode, stream=stream, source=source),
                    observed=observed,
                    expected=expected,
                )
            )

        for stream, relative, episodes in _video_files(dataset):
            times = _probe(dataset, relative).frame_times
            ordered = sorted(episodes, key=lambda item: item.video_ranges.get(stream, (0.0, 0.0))[0])
            previous_end: float | None = None
            for episode in ordered:
                start, end = episode.video_ranges.get(stream, (0.0, 0.0))
                if previous_end is not None and abs(start - previous_end) > tolerance:
                    add(
                        f"{episode.identifier} video range does not continue from the previous episode",
                        episode.identifier,
                        stream,
                        relative,
                        {"from_timestamp": start},
                        {"from_timestamp": previous_end},
                    )
                previous_end = end
                stored = int(np.count_nonzero((times >= start - tolerance) & (times < end - tolerance)))
                if stored != episode.length:
                    add(
                        f"{episode.identifier} video range holds {stored} frames for {episode.length} samples",
                        episode.identifier,
                        stream,
                        relative,
                        {"frames": stored},
                        {"frames": episode.length},
                    )
            if times.size and previous_end is not None:
                file_end = float(times[-1]) + interval
                if abs(file_end - previous_end) > tolerance:
                    add(
                        f"{relative} ends at {file_end:.3f} s but its last episode range ends at {previous_end:.3f} s",
                        None,
                        stream,
                        relative,
                        {"file_end_seconds": file_end},
                        {"file_end_seconds": previous_end},
                    )
            if len(findings) >= options["max_findings"]:
                break
        return findings[: int(options["max_findings"])]


class CameraIdentityRule:
    metadata = RuleMetadata(
        id="video.camera_identity",
        version="1.0.0",
        title="Each episode's camera views match their stream",
        description="A view that looks like another camera's stream gives a policy the wrong viewpoint.",
        severity=Severity.WARNING,
        scope="episode",
        cost="video",
        required_capabilities=frozenset({"video", "episodes"}),
        option_defaults={"min_episodes": 5, "max_findings": 50},
        limitations="Compares episodes with the dataset, so a swap that covers every episode is not detectable.",
        remediation="Check camera naming for the cited episodes and correct the stream mapping.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        streams = _video_streams(dataset)
        episodes = dataset.inventory.episodes
        if len(streams) < 2 or len(episodes) < int(options["min_episodes"]):
            raise RuleNotApplicable("needs two cameras and several episodes")
        frames: dict[str, dict[str, np.ndarray]] = {stream: {} for stream in streams}
        for episode in episodes:
            for stream in streams:
                if stream in episode.video_files:
                    mean = dataset.video_analysis(episode, stream).mean_frame
                    if mean.size:
                        frames[stream][episode.identifier] = mean
        centers = {}
        for stream, items in frames.items():
            if len({item.shape for item in items.values()}) != 1 or not items:
                raise RuleNotApplicable("camera frames do not share one size within a stream")
            centers[stream] = np.median(np.stack(list(items.values())), axis=0)
        findings = []
        for stream, items in frames.items():
            for identifier, mean in items.items():
                own = float(np.mean(np.abs(mean - centers[stream])))
                for other, center in centers.items():
                    if other == stream or center.shape != mean.shape:
                        continue
                    distance = float(np.mean(np.abs(mean - center)))
                    if distance < own * 0.5:
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"{stream} in {identifier} looks like {other}",
                                location=Location(episode=identifier, stream=stream),
                                observed={"distance_to_own": own, "distance_to_other": distance, "other": other},
                                expected="closest to its own stream",
                            )
                        )
                        break
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings


def _video_files(dataset: DatasetView) -> Iterator[tuple[str, str, list[Episode]]]:
    for stream in _video_streams(dataset):
        files: dict[str, list[Episode]] = {}
        for episode in dataset.inventory.episodes:
            relative = episode.video_files.get(stream)
            if relative is not None and (dataset.root / relative).is_file():
                files.setdefault(relative, []).append(episode)
        for relative, episodes in sorted(files.items()):
            yield stream, relative, episodes


def _probe(dataset: DatasetView, relative: str) -> VideoProbe:
    method = getattr(dataset, "video_probe", None)
    probe: VideoProbe | None = method(relative) if method is not None else None
    if probe is None:
        raise RuleNotApplicable("container checks require PyAV; install physlint[video]")
    return probe


def _episode_at(episodes: list[Episode], stream: str, moment: float | None) -> str | None:
    if moment is None:
        return None
    for episode in episodes:
        start, end = episode.video_ranges.get(stream, (0.0, 0.0))
        if start <= moment < end:
            return episode.identifier
    return None


VIDEO_RULES: list[Rule] = [
    VideoDecodeRule(),
    FrozenFramesRule(),
    RepeatedFramesRule(),
    BlackFramesRule(),
    BitstreamRule(),
    VideoTimelineRule(),
    CameraIdentityRule(),
]
