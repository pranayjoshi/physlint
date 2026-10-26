from __future__ import annotations

import json
import shutil

import numpy as np
import pyarrow.parquet as pq
import pytest

from physlint.adapters.base import AdapterError
from physlint.api import check_dataset
from physlint.config import CacheSettings, Config
from physlint.engine.discovery import discover


def convert_fixture(root, version, *, chunks_size=1):
    info_path = root / "meta/info.json"
    info = json.loads(info_path.read_text())
    info.update(
        codebase_version=version,
        chunks_size=chunks_size,
        data_path="data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet",
        video_path="videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4",
    )
    table = pq.read_table(root / "data/chunk-000/file-000.parquet")
    records = pq.read_table(root / "meta/episodes/chunk-000/file-000.parquet").to_pylist()
    for record in records:
        index = record["episode_index"]
        destination = root / info["data_path"].format(episode_chunk=index // chunks_size, episode_index=index)
        destination.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table.slice(record["dataset_from_index"], record["length"]), destination)
    (root / "meta/episodes.jsonl").write_text(
        "".join(
            json.dumps(
                {
                    "episode_index": record["episode_index"],
                    "length": record["length"],
                    "tasks": record["tasks"],
                }
            )
            + "\n"
            for record in records
        )
    )
    shutil.rmtree(root / "meta/episodes")
    info_path.write_text(json.dumps(info))
    return root


@pytest.mark.parametrize("version", ["v2.0", "v2.1"])
def test_v2_validates_bounded_episode_files_and_detects_nan(dataset_factory, version):
    root = convert_fixture(dataset_factory(), version)
    view = discover(root)
    assert view.version == version.removeprefix("v")
    assert view.inventory.episodes[1].data_file == "data/chunk-001/episode_000001.parquet"
    batches = list(view.iter_batches(view.inventory.episodes[1], ("action",), batch_size=2))
    assert [len(batch.columns["action"]) for batch in batches] == [2, 2, 2]
    settings = Config(cache=CacheSettings(enabled=False))
    assert check_dataset(root, config=settings).summary.findings == 0
    actions = [[float(i), 0.0] for i in range(12)]
    actions[8][0] = float("nan")
    dirty = convert_fixture(dataset_factory(actions=actions), version)
    report = check_dataset(dirty, config=settings)
    finding = next(f for r in report.results for f in r.findings if f.rule_id == "numeric.finite_values")
    assert finding.location.episode == "episode_000001"
    assert finding.location.sample_index == 2


@pytest.mark.parametrize("version", ["v2.0", "v2.1"])
def test_v2_videos_have_independent_time_ranges(dataset_factory, version):
    import cv2

    root = convert_fixture(dataset_factory(include_video=True), version)
    source = cv2.VideoCapture(str(root / "videos/observation.images.wrist/chunk-000/file-000.mp4"))
    try:
        for episode in discover(root).inventory.episodes:
            path = root / episode.video_files["observation.images.wrist"]
            path.parent.mkdir(parents=True, exist_ok=True)
            writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 30, (64, 48))
            try:
                for _ in range(episode.length):
                    ok, frame = source.read()
                    assert ok
                    writer.write(frame)
            finally:
                writer.release()
    finally:
        source.release()
    view = discover(root)
    for episode in view.inventory.episodes:
        frames = list(view.iter_video_frames(episode, "observation.images.wrist"))
        assert len(frames) == 6
        assert frames[0].timestamp == 0
        assert np.isfinite(frames[0].image).all()
    report = check_dataset(root, config=Config(cache=CacheSettings(enabled=False)))
    assert report.summary.errored == 0
    assert next(r for r in report.results if r.rule_id == "video.decode").status == "passed"


@pytest.mark.parametrize("payload", ["{broken", "[]\n", '{"episode_index": 0}\n'])
def test_v2_malformed_episodes_fail_as_source_errors(dataset_factory, payload):
    root = convert_fixture(dataset_factory(), "v2.0")
    (root / "meta/episodes.jsonl").write_text(payload)
    with pytest.raises(AdapterError):
        discover(root)


def test_v2_missing_video_is_a_finding(dataset_factory):
    root = convert_fixture(dataset_factory(include_video=True), "v2.1")
    report = check_dataset(root, config=Config(cache=CacheSettings(enabled=False)))
    assert next(r for r in report.results if r.rule_id == "manifest.required_files").status == "failed"
