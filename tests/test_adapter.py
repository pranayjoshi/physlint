from __future__ import annotations

import json

import pytest

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
