from __future__ import annotations

import hashlib
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import RuleStatus
from validation.benchmark import (
    MCAP_BENIGN,
    MCAP_DEFECTS,
    RECIPES,
    SYNTHETIC_SCENES,
    DatasetBench,
    benchmark_config,
    build_synthetic,
    classify,
    link_workspace,
    macro_rate,
    render_markdown,
    replace_parquet,
    run_dataset,
    run_mcap,
    summarize,
    wilson,
)


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        if path.is_file():
            digest.update(str(path.relative_to(root)).encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()


def long_dataset(dataset_factory, **options) -> Path:
    return dataset_factory(episode_lengths=(40, 40), **options)


def test_workspace_replacement_never_reaches_the_source(dataset_factory, tmp_path):
    source = long_dataset(dataset_factory)
    before = tree_digest(source)
    workspace = tmp_path / "workspace"
    link_workspace(source, workspace)
    path = workspace / "data" / "chunk-000" / "file-000.parquet"
    assert path.is_symlink()
    replace_parquet(path, pa.table({"replaced": [1]}))
    assert not path.is_symlink()
    assert tree_digest(source) == before


def test_full_run_leaves_source_unchanged_and_is_deterministic(dataset_factory, tmp_path):
    source = long_dataset(dataset_factory)
    before = tree_digest(source)
    first = run_dataset("fixture", source, tmp_path / "one", 1, {"numeric", "temporal", "index", "metadata", "benign"})
    second = run_dataset("fixture", source, tmp_path / "two", 1, {"numeric", "temporal", "index", "metadata", "benign"})
    assert tree_digest(source) == before
    assert first == second
    assert first["clean_status"] == "passed"
    assert {row["outcome"] for row in first["trials"] if row["benign"]} <= {"clean", "skipped"}


@pytest.mark.parametrize(
    ("recipe", "level", "rule"),
    [
        ("nan_action", 1, "numeric.finite_values"),
        ("nan_timestamp", 1, "temporal.monotonic"),
        ("frame_index_reset", None, "episode.index_columns"),
        ("exact_duplicate", None, "duplication.exact_episodes"),
        ("missing_data_file", None, "manifest.required_files"),
    ],
)
def test_known_defects_are_credited_to_their_rule(dataset_factory, tmp_path, recipe, level, rule):
    bench = DatasetBench("fixture", long_dataset(dataset_factory), tmp_path)
    row = bench.trial(RECIPES[recipe], level, 0)
    assert row["detected"] is True
    assert rule in row["rules"]


def test_stale_file_pointer_reproduces_issue_2401(dataset_factory, tmp_path):
    source = long_dataset(dataset_factory)
    bench = DatasetBench("fixture", source, tmp_path)
    bench._target = lambda _rng: bench.inventory.episodes[1]  # the boundary episode cannot start the file
    row = bench.trial(RECIPES["stale_file_pointer"], None, 0)
    assert row["outcome"] == "localized"
    assert "episode.valid_boundaries" in row["rules"]


def test_undetectable_defect_is_recorded_as_missed(dataset_factory, tmp_path):
    bench = DatasetBench("fixture", long_dataset(dataset_factory), tmp_path)
    row = bench.trial(RECIPES["action_shift"], 5, 0)
    assert row["outcome"] == "missed"


def test_video_recipes_keep_source_and_use_a_control(dataset_factory, tmp_path):
    pytest.importorskip("cv2")
    source = long_dataset(dataset_factory, include_video=True)
    before = tree_digest(source)
    bench = DatasetBench("fixture", source, tmp_path)
    missing = bench.trial(RECIPES["video_missing"], None, 0)
    black = bench.trial(RECIPES["black_frames"], 3, 0)
    assert missing["detected"] is True
    assert "video.black_frames" in black["rules"]
    assert tree_digest(source) == before


def test_untouched_video_statistics_are_reused(dataset_factory, tmp_path, monkeypatch):
    pytest.importorskip("cv2")
    from physlint.adapters.lerobot import LeRobotAdapter

    bench = DatasetBench("fixture", long_dataset(dataset_factory, include_video=True), tmp_path)

    def fail(*_args, **_kwargs):
        raise AssertionError("untouched video was decoded again")

    monkeypatch.setattr(LeRobotAdapter, "iter_video_frames", fail)
    assert bench.trial(RECIPES["nan_action"], 1, 0)["detected"] is True


def test_classification_credits_only_target_or_dataset_findings():
    other = {("video.frozen_frames", "episode_000009", "blocking")}
    assert classify(other, {"episode_000001"})["outcome"] == "missed"
    assert classify({("a", "episode_000001", "advisory")}, {"episode_000001"})["blocks_ci"] is False
    assert classify({("a", None, "blocking")}, {"episode_000001"})["outcome"] == "dataset_level"
    assert classify({("a", None, "errored")}, {"episode_000001"})["outcome"] == "failed_closed"


def test_wilson_interval_and_macro_rate():
    low, high = wilson(0, 10)
    assert low == 0 and 0.2 < high < 0.35
    rows = [
        {"recipe": "a", "detected": True},
        {"recipe": "a", "detected": True},
        {"recipe": "a", "detected": True},
        {"recipe": "b", "detected": False},
    ]
    assert macro_rate(rows) == 0.5


def test_summary_renders_from_real_trials(dataset_factory, tmp_path):
    result = run_dataset("fixture", long_dataset(dataset_factory), tmp_path, 1, {"numeric", "benign"})
    summary = summarize([result], {"fixture": "synthetic"})
    assert summary["by_split"]["synthetic"]["macro_detection"] is not None
    assert "| `nan_action` |" in render_markdown(summary, "test")


def test_recipe_registry_covers_required_categories():
    categories = {item.category for item in RECIPES.values()}
    assert categories == {"numeric", "temporal", "index", "metadata", "video", "benign"}
    assert sum(not item.benign for item in RECIPES.values()) >= 30


def test_synthetic_scene_is_valid_lerobot_data(tmp_path):
    pytest.importorskip("cv2")
    root = build_synthetic(tmp_path / "scene", SYNTHETIC_SCENES["synth-arm-large"], episodes=2, length=40)
    bench = DatasetBench("scene", root, tmp_path / "work")
    assert bench.clean.summary.errored == 0
    assert bench.clean.status == "passed"


def test_mcap_track_is_clean_at_baseline_and_detects_known_defects(tmp_path):
    result = run_mcap(tmp_path, 1)
    assert result["clean_status"] == "passed"
    outcomes = {row["recipe"]: row for row in result["trials"]}
    assert set(outcomes) == {*MCAP_DEFECTS, *MCAP_BENIGN}
    assert "ros2.semantic_consistency" in outcomes["nan_joint"]["rules"]
    assert outcomes["chunk_byte_flip"]["detected"] is True
    assert "ros2.required_topics" in outcomes["missing_topic"]["rules"]


@pytest.fixture(scope="module")
def scene_bench(tmp_path_factory):
    pytest.importorskip("cv2")
    work = tmp_path_factory.mktemp("scene")
    root = build_synthetic(work / "source", SYNTHETIC_SCENES["synth-arm-large"], episodes=8, length=90)
    return DatasetBench("scene", root, work / "trials")


def test_synthetic_clean_scene_has_no_findings_from_any_rule(scene_bench):
    flagged = {result.rule_id: len(result.findings) for result in scene_bench.clean.results if result.findings}
    assert flagged == {}
    assert scene_bench.clean.summary.errored == 0


@pytest.mark.parametrize(
    ("recipe", "level", "rule"),
    [
        ("action_spike", 10.0, "numeric.outlier_jumps"),
        ("unit_flip", None, "numeric.episode_envelope"),
        ("stuck_joint", None, "numeric.stuck_channels"),
        ("dead_action", None, "numeric.stuck_channels"),
        ("sensor_noise", 5.0, "numeric.noise_level"),
        ("joint_permutation", None, "numeric.action_state_coupling"),
        ("action_shift", 30, "temporal.signal_alignment"),
        ("near_duplicate", None, "duplication.near_episodes"),
        ("timestamp_offset", None, "temporal.episode_start"),
        ("clock_scale", 1.1, "temporal.clock_drift"),
        ("saturated_frames", 3, "video.black_frames"),
        ("half_rate_camera", None, "video.repeated_frames"),
        ("frozen_camera", 60, "video.frozen_frames"),
        ("video_range_drift", 15, "video.timeline"),
    ],
)
def test_new_rules_catch_their_defect_end_to_end(scene_bench, recipe, level, rule):
    assert rule in scene_bench.trial(RECIPES[recipe], level, 0)["rules"]


def test_null_row_in_fixed_size_column_fails_closed_with_a_clear_reason(dataset_factory, tmp_path):
    source = long_dataset(dataset_factory)
    bench = DatasetBench("fixture", source, tmp_path)
    assert bench.trial(RECIPES["null_action_row"], None, 0)["outcome"] in {"failed_closed", "localized"}
    workspace = tmp_path / "workspace"
    link_workspace(source, workspace)
    path = workspace / "data" / "chunk-000" / "file-000.parquet"
    table = pq.read_table(path)
    values = table["observation.state"].to_pylist()
    values[3] = None
    position = table.schema.get_field_index("observation.state")
    replace_parquet(
        path,
        table.set_column(
            position, table.schema.field(position), pa.array(values, type=table.schema.field(position).type)
        ),
    )
    report = run_validation(discover(workspace), benchmark_config(), allow_config_plugins=False)
    reasons = [result.reason or "" for result in report.results if result.status == RuleStatus.ERRORED]
    assert any("fixed-size list" in reason for reason in reasons)


def test_small_mcap_reorder_and_publisher_interleave_do_not_warn(tmp_path):
    result = run_mcap(tmp_path, 1)
    assert {row["recipe"]: row["outcome"] for row in result["trials"] if row["benign"]} == {
        "benign_arrival_reorder": "clean",
        "benign_two_publishers": "clean",
    }
    assert "mcap.timestamp_order" in next(row for row in result["trials"] if row["recipe"] == "log_rollback")["rules"]


def test_video_corruption_is_reported_across_seeds(scene_bench):
    assert sum(scene_bench.trial(RECIPES["video_bitflips"], 200, seed)["detected"] for seed in range(4)) >= 2
