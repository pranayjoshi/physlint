from __future__ import annotations

import json
from pathlib import Path

import pytest

from physlint.adapters import lerobot as lerobot_module
from physlint.adapters.base import AdapterError
from physlint.api import inspect_dataset
from physlint.engine.discovery import discover, is_lerobot


def test_discovers_and_inventories_lerobot_v3(dataset_factory):
    root = dataset_factory()
    assert is_lerobot(root)
    inventory = inspect_dataset(root)
    assert inventory.adapter == "lerobot"
    assert inventory.format_version == "v3.0"
    assert inventory.total_frames == 12
    assert len(inventory.episodes) == 2
    assert {stream.key for stream in inventory.streams} >= {"observation.state", "action"}


def test_iterates_each_episode_lazily(dataset_factory):
    dataset = discover(dataset_factory())
    batches = list(dataset.iter_batches(dataset.inventory.episodes[1], ("timestamp", "action"), 2))
    assert sum(len(batch.columns["timestamp"]) for batch in batches) == 6
    assert batches[0].columns["timestamp"][0] == 0
    assert batches[0].columns["action"].shape[1:] == (2,)


def test_rejects_legacy_or_malformed_metadata(dataset_factory):
    root = dataset_factory()
    info_path = root / "meta" / "info.json"
    info = json.loads(info_path.read_text(encoding="utf-8"))
    info["codebase_version"] = "v2.1"
    info_path.write_text(json.dumps(info), encoding="utf-8")
    with pytest.raises(AdapterError, match="supports v3"):
        discover(root, "lerobot")


def test_infers_hugging_face_repo_and_revision_from_snapshot_path(dataset_factory, tmp_path: Path):
    root = dataset_factory(repo_id=None)
    snapshot = tmp_path / "hub" / "datasets--example-org--robot-data" / "snapshots" / "abc123"
    snapshot.parent.mkdir(parents=True)
    root.rename(snapshot)

    dataset = discover(snapshot)
    assert dataset.inventory.name == "example-org/robot-data"
    assert dataset.inventory.source_revision == "abc123"


def test_explains_pyarrow_repetition_level_bug(dataset_factory, monkeypatch):
    root = dataset_factory()

    def broken_read_table(*args, **kwargs):
        raise OSError("Repetition level histogram size mismatch")

    monkeypatch.setattr(lerobot_module.pq, "read_table", broken_read_table)
    with pytest.raises(AdapterError, match="upgrade PyArrow to >=19.0.1"):
        discover(root, "lerobot")
