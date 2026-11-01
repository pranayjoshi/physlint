"""Checks calibrated from the dataset itself, needing no robot-specific configuration.

Each rule compares an episode with its own dataset, so these rules report anomalies rather
than proof of a defect. They default to warnings and need several episodes to compare.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from weakref import WeakKeyDictionary

import numpy as np

from physlint.models.dataset import DatasetView, Episode
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata, RuleNotApplicable
from physlint.rules.common import finding, numeric_streams
from physlint.rules.video import _video_streams

_MATRICES: WeakKeyDictionary[Any, dict[str, dict[str, np.ndarray]]] = WeakKeyDictionary()


def _load_stream(dataset: DatasetView, stream: str) -> dict[str, np.ndarray]:
    """Return one stream per episode as finite, two-dimensional float arrays, caching per adapter."""
    cache = _MATRICES.setdefault(dataset, {})
    if stream in cache:
        return cache[stream]
    loaded: dict[str, np.ndarray] = {}
    for episode in dataset.inventory.episodes:
        if stream not in dataset.parquet_schema(episode):
            continue
        chunks = [batch.columns[stream] for batch in dataset.iter_batches(episode, (stream,))]
        if not chunks:
            continue
        try:
            joined = np.concatenate(chunks)
            values = np.asarray(joined, dtype=float).reshape(len(joined), -1)
        except (TypeError, ValueError):
            continue
        if len(values) >= 3 and np.all(np.isfinite(values)):
            loaded[episode.identifier] = values
    cache[stream] = loaded
    return loaded


def _float_streams(dataset: DatasetView, options: dict[str, Any]) -> list[str]:
    requested = list(options["streams"]) or numeric_streams(dataset)
    kept = []
    for stream in requested:
        declared = next((item for item in dataset.inventory.streams if item.key == stream), None)
        if declared is not None and "float" in declared.dtype.lower():
            kept.append(stream)
    return kept


def _require_episodes(items: dict[str, np.ndarray], minimum: int) -> bool:
    return len(items) >= minimum


def _mad(values: np.ndarray) -> float:
    return float(1.4826 * np.median(np.abs(values - np.median(values))))


def _not_common(flags: np.ndarray, limit: float = 0.1) -> np.ndarray:
    """Keep only dimensions flagged rarely: a pattern shared by many episodes is not an outlier."""
    allowed = max(1, int(np.ceil(flags.shape[0] * limit)))
    return np.asarray(np.sum(flags, axis=0) <= allowed, dtype=bool)


def _sample_noise(values: np.ndarray) -> np.ndarray:
    return np.asarray(1.4826 * np.median(np.abs(np.diff(values, n=2, axis=0)), axis=0) / np.sqrt(6.0), dtype=float)


class JumpsRule:
    metadata = RuleMetadata(
        id="numeric.outlier_jumps",
        version="1.0.0",
        title="Streams have no jumps far beyond their own normal steps",
        description="A one-sample jump far beyond a stream's usual step suggests a spike, reset, or unit change.",
        severity=Severity.WARNING,
        scope="sample",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"streams": [], "step_factor": 5.0, "min_range_fraction": 0.05, "max_findings": 50},
        limitations="Skips dimensions with few distinct values, such as binary grippers.",
        remediation="Inspect the cited sample for sensor spikes, encoder resets, or a change of units.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        for stream in _float_streams(dataset, options):
            items = _load_stream(dataset, stream)
            if not items:
                continue
            everything = np.concatenate(list(items.values()))
            # Per-episode medians keep one corrupted episode from raising its own limit.
            usual = np.median(np.stack([np.abs(np.diff(v, axis=0)).max(axis=0) for v in items.values()]), axis=0)
            spread = np.median(np.stack([np.ptp(v, axis=0) for v in items.values()]), axis=0)
            limit = np.maximum(usual * float(options["step_factor"]), spread * float(options["min_range_fraction"]))
            discrete = np.array([np.unique(everything[:, dim]).size <= 8 for dim in range(everything.shape[1])])
            for identifier, values in items.items():
                delta = np.abs(np.diff(values, axis=0))
                bad = (delta > limit) & ~discrete & (spread > 0)
                rows = np.flatnonzero(np.any(bad, axis=1))
                if rows.size:
                    row = int(rows[0])
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{stream} jumps far beyond its usual step in {identifier}",
                            location=Location(episode=identifier, stream=stream, sample_index=row + 1),
                            observed={"jumps": int(rows.size), "largest_step": float(delta[row].max())},
                            expected={"step_limit": limit.tolist()},
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        return findings


class EnvelopeRule:
    metadata = RuleMetadata(
        id="numeric.episode_envelope",
        version="1.0.0",
        title="Episodes stay within the dataset's usual range",
        description="An episode far outside the range of the others suggests a unit, calibration, or sign change.",
        severity=Severity.WARNING,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"streams": [], "min_episodes": 5, "spread_factor": 1.0, "max_findings": 50},
        limitations="Needs several episodes; a change shared by every episode is not detectable.",
        remediation="Compare the cited episode's units and calibration with the rest of the dataset.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        minimum = int(options["min_episodes"])
        compared = False
        for stream in _float_streams(dataset, options):
            items = _load_stream(dataset, stream)
            if not _require_episodes(items, minimum):
                continue
            compared = True
            highs = np.stack([values.max(axis=0) for values in items.values()])
            lows = np.stack([values.min(axis=0) for values in items.values()])
            high_mark, low_mark = np.percentile(highs, 90, axis=0), np.percentile(lows, 10, axis=0)
            margin = float(options["spread_factor"]) * np.maximum(high_mark - low_mark, 1e-9)
            outside = (highs > high_mark + margin) | (lows < low_mark - margin)
            outside &= _not_common(outside)
            for position, identifier in enumerate(items):
                if np.any(outside[position]):
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{stream} leaves the dataset's usual range in {identifier}",
                            location=Location(episode=identifier, stream=stream),
                            observed={"dimensions": np.flatnonzero(outside[position]).tolist()},
                            expected="within the range of comparable episodes",
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        if not compared:
            raise RuleNotApplicable("needs several episodes to compare")
        return findings


class StuckChannelsRule:
    metadata = RuleMetadata(
        id="numeric.stuck_channels",
        version="1.0.0",
        title="Channels that normally vary do not stick",
        description="A channel constant for a whole episode, while it varies elsewhere, suggests a dead sensor.",
        severity=Severity.WARNING,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"streams": [], "min_episodes": 5, "min_varying_fraction": 0.9, "max_findings": 50},
        limitations="An unused joint or idle demonstration can look identical to a dead sensor.",
        remediation="Check the sensor or teleoperation link for the cited episode.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        minimum = int(options["min_episodes"])
        compared = False
        for stream in _float_streams(dataset, options):
            items = _load_stream(dataset, stream)
            if not _require_episodes(items, minimum):
                continue
            compared = True
            constant = np.stack([np.ptp(values, axis=0) == 0 for values in items.values()])
            # Exclude one episode from the count so the episode under test cannot lower the bar.
            usually_varies = np.sum(~constant, axis=0) >= float(options["min_varying_fraction"]) * (len(items) - 1)
            for position, identifier in enumerate(items):
                stuck = constant[position] & usually_varies
                if np.any(stuck):
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{stream} has constant channels in {identifier}",
                            location=Location(episode=identifier, stream=stream),
                            observed={"dimensions": np.flatnonzero(stuck).tolist()},
                            expected="channels vary as in other episodes",
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        if not compared:
            raise RuleNotApplicable("needs several episodes to compare")
        return findings


class NoiseLevelRule:
    metadata = RuleMetadata(
        id="numeric.noise_level",
        version="1.0.0",
        title="Episode noise matches the dataset",
        description="Much higher sample noise than comparable episodes suggests a failing sensor or transport.",
        severity=Severity.WARNING,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"streams": [], "min_episodes": 5, "noise_ratio": 5.0, "max_findings": 50},
        limitations="Needs several episodes; noise shared by every episode is not detectable.",
        remediation="Inspect the sensor and its transport for the cited episode.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        minimum = int(options["min_episodes"])
        compared = False
        for stream in _float_streams(dataset, options):
            items = _load_stream(dataset, stream)
            if not _require_episodes(items, minimum):
                continue
            compared = True
            noise = np.stack([_sample_noise(values) for values in items.values()])
            usual = np.median(noise, axis=0)
            spread = np.ptp(np.concatenate(list(items.values())), axis=0)
            floor = np.maximum(usual, spread * 1e-3)
            loud = (noise > floor * float(options["noise_ratio"])) & (spread > 0)
            loud &= _not_common(loud)
            for position, identifier in enumerate(items):
                if np.any(loud[position]):
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{stream} is unusually noisy in {identifier}",
                            location=Location(episode=identifier, stream=stream),
                            observed={"dimensions": np.flatnonzero(loud[position]).tolist()},
                            expected={"noise_ratio_below": options["noise_ratio"]},
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        if not compared:
            raise RuleNotApplicable("needs several episodes to compare")
        return findings


class ActionStateCouplingRule:
    metadata = RuleMetadata(
        id="numeric.action_state_coupling",
        version="1.0.0",
        title="State follows action as it does elsewhere in the dataset",
        description="A joint whose state stops tracking its action suggests swapped joints or a sign change.",
        severity=Severity.WARNING,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        required_streams=frozenset({"action", "observation.state"}),
        option_defaults={"min_episodes": 5, "min_usual_correlation": 0.7, "max_drop": 0.5, "max_findings": 50},
        limitations="Runs only when action and state have the same dimensions and usually track each other.",
        remediation="Check joint ordering and signs in the cited episode.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        actions = _load_stream(dataset, "action")
        states = _load_stream(dataset, "observation.state")
        shared = [
            identifier
            for identifier in actions
            if identifier in states and actions[identifier].shape == states[identifier].shape
        ]
        if len(shared) < int(options["min_episodes"]):
            raise RuleNotApplicable("needs several episodes with matching action and state dimensions")
        shapes = {actions[item].shape[1] for item in shared}
        if len(shapes) != 1:
            raise RuleNotApplicable("episodes do not share one action dimension")
        correlations = np.stack([_correlation(actions[item], states[item]) for item in shared])
        usual = np.nanmedian(correlations, axis=0)
        findings = []
        for position, identifier in enumerate(shared):
            broken = (usual >= float(options["min_usual_correlation"])) & (
                correlations[position] < usual - float(options["max_drop"])
            )
            if np.any(broken):
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"State stops tracking action in {identifier}",
                        location=Location(episode=identifier, stream="observation.state"),
                        observed={"dimensions": np.flatnonzero(broken).tolist()},
                        expected={"usual_correlation": usual.tolist()},
                    )
                )
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings


def _correlation(first: np.ndarray, second: np.ndarray) -> np.ndarray:
    a = first - first.mean(axis=0)
    b = second - second.mean(axis=0)
    denominator = np.sqrt((a**2).sum(axis=0) * (b**2).sum(axis=0))
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(denominator > 0, (a * b).sum(axis=0) / denominator, np.nan)


@dataclass(frozen=True)
class _Lag:
    lag: int
    strength: float


def _best_lag(reference: np.ndarray, signal: np.ndarray, limit: int) -> _Lag:
    """Find how many samples ``signal`` trails ``reference`` by normalized cross-correlation."""
    size = min(reference.size, signal.size)
    first = reference[:size] - reference[:size].mean()
    second = signal[:size] - signal[:size].mean()
    scale = float(np.sqrt((first**2).sum() * (second**2).sum()))
    if scale == 0 or size < 8:
        return _Lag(0, 0.0)
    best = _Lag(0, -1.0)
    for lag in range(-limit, limit + 1):
        if lag >= 0:
            value = float(np.dot(first[: size - lag], second[lag:]))
        else:
            value = float(np.dot(first[-lag:], second[: size + lag]))
        strength = value / scale
        if strength > best.strength or (strength == best.strength and abs(lag) < abs(best.lag)):
            best = _Lag(lag, strength)
    return best


def _speed(values: np.ndarray) -> np.ndarray:
    scale = np.maximum(np.ptp(values, axis=0), 1e-9)
    speed = np.sqrt(np.mean((np.diff(values, axis=0) / scale) ** 2, axis=1))
    return np.convolve(speed, np.ones(3) / 3, mode="same")


class SignalAlignmentRule:
    metadata = RuleMetadata(
        id="temporal.signal_alignment",
        version="1.0.0",
        title="Action, state, and video stay aligned as they do elsewhere",
        description="An episode whose signals are shifted against each other teaches a policy the wrong timing.",
        severity=Severity.WARNING,
        scope="episode",
        cost="video",
        required_capabilities=frozenset({"numeric", "episodes"}),
        required_streams=frozenset({"observation.state"}),
        option_defaults={"min_episodes": 5, "min_strength": 0.5, "lag_tolerance_frames": 2, "max_findings": 50},
        limitations=(
            "Measures each episode's lag and compares it with the dataset, so a shift shared by every episode is "
            "not detectable. Needs motion that cameras can see and several episodes."
        ),
        remediation="Inspect recorder timing and video ranges for the cited episode.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        states = _load_stream(dataset, "observation.state")
        if len(states) < int(options["min_episodes"]):
            raise RuleNotApplicable("needs several episodes to compare")
        limit = max(3, int(round(float(dataset.inventory.fps or 30.0))))
        by_id: dict[str, Episode] = {episode.identifier: episode for episode in dataset.inventory.episodes}
        findings: list[Finding] = []
        pairs: dict[str, dict[str, _Lag]] = {}
        reversals: dict[str, dict[str, tuple[float, float]]] = {}
        actions = _load_stream(dataset, "action")
        pairs["action"] = {
            identifier: _best_lag(_speed(actions[identifier]), _speed(values), limit)
            for identifier, values in states.items()
            if identifier in actions and len(actions[identifier]) == len(values)
        }
        for stream in _video_streams(dataset):
            measured: dict[str, _Lag] = {}
            reversal: dict[str, tuple[float, float]] = {}
            for identifier, values in states.items():
                episode = by_id[identifier]
                if stream not in episode.video_files:
                    continue
                change = dataset.video_analysis(episode, stream).mean_absolute_differences
                speed = _speed(values)
                if change.size < 8:
                    continue
                forward = _best_lag(speed, change, limit)
                measured[identifier] = forward
                reversal[identifier] = (forward.strength, _best_lag(speed, change[::-1], limit).strength)
            pairs[stream] = measured
            reversals[stream] = reversal
        strength_limit = float(options["min_strength"])
        tolerance = int(options["lag_tolerance_frames"])
        for name, measured in pairs.items():
            strong = [item.lag for item in measured.values() if item.strength >= strength_limit]
            if len(strong) < int(options["min_episodes"]):
                continue
            usual = float(np.median(strong))
            allowed = max(tolerance, 4.0 * _mad(np.asarray(strong, dtype=float)))
            for identifier, item in measured.items():
                if item.strength >= strength_limit and abs(item.lag - usual) > allowed:
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{name} is {item.lag - usual:+.0f} frames off the dataset's usual timing in {identifier}",
                            location=Location(episode=identifier, stream=name),
                            observed={"lag_frames": item.lag, "strength": item.strength},
                            expected={"lag_frames": usual, "tolerance_frames": allowed},
                        )
                    )
        for stream, reversal in reversals.items():
            usual_gain = [ahead - behind for ahead, behind in reversal.values()]
            if len(usual_gain) < int(options["min_episodes"]) or float(np.median(usual_gain)) <= 0.05:
                continue
            for identifier, (ahead, behind) in reversal.items():
                if behind >= strength_limit and behind - ahead > 0.15:
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{stream} matches robot motion better when reversed in {identifier}",
                            location=Location(episode=identifier, stream=stream),
                            observed={"forward_strength": ahead, "reversed_strength": behind},
                            expected="video follows robot motion forward in time",
                        )
                    )
        return findings[: int(options["max_findings"])]


class NearDuplicateEpisodesRule:
    metadata = RuleMetadata(
        id="duplication.near_episodes",
        version="1.0.0",
        title="Episodes are not near-exact copies",
        description="Copies with tiny differences waste training budget and leak evaluation signal.",
        severity=Severity.WARNING,
        scope="dataset",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        required_streams=frozenset({"action"}),
        option_defaults={"max_relative_distance": 0.001, "max_findings": 50},
        limitations="Compares action trajectories of equal length; exact copies belong to duplication.exact_episodes.",
        remediation="Keep one copy of the demonstration and drop or recollect the rest.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        items = _load_stream(dataset, "action")
        if len(items) < 2:
            raise RuleNotApplicable("needs at least two episodes")
        scale = np.maximum(np.concatenate(list(items.values())).std(axis=0), 1e-9)
        by_shape: dict[tuple[int, ...], list[tuple[str, np.ndarray]]] = {}
        for identifier, values in items.items():
            by_shape.setdefault(values.shape, []).append((identifier, values / scale))
        findings: list[Finding] = []
        limit = float(options["max_relative_distance"])
        for group in by_shape.values():
            if len(group) < 2:
                continue
            matrix = np.stack([values.reshape(-1) for _identifier, values in group])
            for position in range(1, len(group)):
                distance = np.sqrt(np.mean((matrix[:position] - matrix[position]) ** 2, axis=1))
                closest = int(np.argmin(distance))
                if 0 < distance[closest] <= limit:
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{group[position][0]} is a near copy of {group[closest][0]}",
                            location=Location(episode=group[position][0], stream="action"),
                            observed={"duplicate_of": group[closest][0], "relative_distance": float(distance[closest])},
                            expected={"relative_distance_above": limit},
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        return findings


STATISTICAL_RULES: list[Rule] = [
    JumpsRule(),
    EnvelopeRule(),
    StuckChannelsRule(),
    NoiseLevelRule(),
    ActionStateCouplingRule(),
    SignalAlignmentRule(),
    NearDuplicateEpisodesRule(),
]
