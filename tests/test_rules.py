from __future__ import annotations

import math

from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import RuleStatus


def result_for(root, rule_id: str, config: Config | None = None):
    report = run_validation(discover(root), config or Config())
    return next(result for result in report.results if result.rule_id == rule_id)


def test_clean_fixture_passes_universal_rules(dataset_factory):
    report = run_validation(discover(dataset_factory()), Config())
    assert report.status == "passed"
    assert report.summary.errored == 0
    assert report.summary.passed >= 10


def test_nonmonotonic_timestamps_are_located(dataset_factory):
    timestamps = [0, 1 / 30, 2 / 30, 1 / 30, 4 / 30, 5 / 30] * 2
    result = result_for(dataset_factory(timestamps=timestamps), "temporal.monotonic")
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].location.episode == "episode_000000"
    assert result.findings[0].location.sample_index == 3


def test_large_gap_is_detected(dataset_factory):
    timestamps = [0, 1 / 30, 2 / 30, 0.5, 0.5 + 1 / 30, 0.5 + 2 / 30] * 2
    result = result_for(dataset_factory(timestamps=timestamps), "temporal.max_gap")
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].observed["max_gap_ms"] > 80


def test_default_gap_limit_scales_with_declared_fps(dataset_factory):
    result = result_for(dataset_factory(fps=4), "temporal.max_gap")
    assert result.status == RuleStatus.PASSED


def test_explicit_gap_limit_is_preserved_and_repeated_gaps_are_grouped(dataset_factory):
    config = Config(rules={"temporal.max_gap": {"options": {"max_gap_ms": 80}}})
    result = result_for(dataset_factory(fps=4), "temporal.max_gap", config)
    assert result.status == RuleStatus.FAILED
    assert len(result.findings) == 2
    assert result.findings[0].observed["count"] == 5


def test_sampling_jitter_is_detected(dataset_factory):
    timestamps = [0, 1 / 30, 2 / 30, 0.11, 4 / 30, 5 / 30] * 2
    result = result_for(dataset_factory(timestamps=timestamps), "temporal.sampling_interval")
    assert result.status == RuleStatus.FAILED


def test_nan_and_infinity_are_detected(dataset_factory):
    states = [[float(i), float(i + 1)] for i in range(12)]
    states[2][0] = math.nan
    states[9][1] = math.inf
    result = result_for(dataset_factory(states=states), "numeric.finite_values")
    assert result.status == RuleStatus.FAILED
    assert {item.location.episode for item in result.findings} == {
        "episode_000000",
        "episode_000001",
    }

    overlap = result_for(dataset_factory(states=states), "temporal.stream_overlap")
    assert overlap.status == RuleStatus.PASSED


def test_required_stream_is_detected(dataset_factory):
    result = result_for(dataset_factory(include_action_declaration=False), "manifest.required_streams")
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].location.stream == "action"


def test_shape_mismatch_is_detected(dataset_factory):
    result = result_for(dataset_factory(declared_state_shape=(3,)), "manifest.shape_consistency")
    assert result.status == RuleStatus.FAILED


def test_null_stream_value_is_incomplete(dataset_factory):
    actions = [[float(i), float(i + 1)] for i in range(12)]
    actions[4] = None
    result = result_for(dataset_factory(actions=actions), "temporal.stream_overlap")
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].location.sample_index == 4


def test_configured_bounds_are_enforced(dataset_factory):
    config = Config(rules={"numeric.configured_bounds": {"options": {"limits": {"action": {"min": -1, "max": 0.5}}}}})
    result = result_for(dataset_factory(), "numeric.configured_bounds", config)
    assert result.status == RuleStatus.FAILED


def test_unconfigured_robot_specific_rules_are_not_run(dataset_factory):
    report = run_validation(discover(dataset_factory()), Config())
    statuses = {result.rule_id: result.status for result in report.results}
    assert statuses["numeric.configured_bounds"] == RuleStatus.NOT_RUN
    assert statuses["numeric.discontinuity"] == RuleStatus.NOT_RUN
    assert statuses["temporal.observation_action_delay"] == RuleStatus.NOT_RUN


def test_discontinuity_is_detected(dataset_factory):
    config = Config(rules={"numeric.discontinuity": {"options": {"max_delta": {"observation.state": 2.0}}}})
    states = [[float(i), float(i + 1)] for i in range(12)]
    states[4] = [100, 100]
    result = result_for(dataset_factory(states=states), "numeric.discontinuity", config)
    assert result.status == RuleStatus.FAILED


def test_video_rules_pass_clean_video(dataset_factory):
    report = run_validation(discover(dataset_factory(include_video=True)), Config())
    statuses = {result.rule_id: result.status for result in report.results}
    assert statuses["video.decode"] == RuleStatus.PASSED
    assert statuses["video.frozen_frames"] == RuleStatus.PASSED
    assert statuses["video.black_frames"] == RuleStatus.PASSED


def test_frozen_video_is_detected(dataset_factory):
    result = result_for(dataset_factory(include_video=True, video_mode="frozen"), "video.frozen_frames")
    assert result.status == RuleStatus.FAILED


def test_static_scene_without_robot_motion_is_not_a_camera_freeze(dataset_factory):
    stationary = [[0.0, 0.0] for _ in range(12)]
    result = result_for(
        dataset_factory(
            include_video=True,
            video_mode="frozen",
            states=stationary,
            actions=stationary,
        ),
        "video.frozen_frames",
    )
    assert result.status == RuleStatus.PASSED


def test_action_motion_takes_priority_over_noisy_observed_state(dataset_factory):
    actions = [[0.0, 0.0] for _ in range(12)]
    result = result_for(
        dataset_factory(include_video=True, video_mode="frozen", actions=actions),
        "video.frozen_frames",
    )
    assert result.status == RuleStatus.PASSED


def test_black_video_is_detected(dataset_factory):
    result = result_for(dataset_factory(include_video=True, video_mode="black"), "video.black_frames")
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].location.episode == "episode_000001"
    assert len(result.findings) == 1
    assert result.findings[0].observed["count"] == 6


def test_video_statistics_are_decoded_once_per_episode_and_stream(dataset_factory, monkeypatch):
    dataset = discover(dataset_factory(include_video=True))
    original = dataset.iter_video_frames
    calls = 0

    def counted(*args, **kwargs):
        nonlocal calls
        calls += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(dataset, "iter_video_frames", counted)
    report = run_validation(dataset, Config())
    assert report.summary.errored == 0
    assert calls == 2


def test_exact_duplicate_episodes_are_detected(dataset_factory):
    states = [[1.0, 2.0] for _ in range(12)]
    actions = [[0.1, 0.2] for _ in range(12)]
    result = result_for(dataset_factory(states=states, actions=actions), "duplication.exact_episodes")
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].location.episode == "episode_000001"
    assert result.findings[0].observed["duplicate_of"] == "episode_000000"
