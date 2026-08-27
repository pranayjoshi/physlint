from __future__ import annotations

from pathlib import Path

import pytest

from physlint.adapters.base import AdapterError
from physlint.api import inspect_dataset
from physlint.engine.discovery import discover, resolve_mcap_source


def test_discovers_generic_mcap_file(mcap_factory):
    path = mcap_factory()
    dataset = discover(path)
    assert dataset.inventory.adapter == "mcap"
    assert dataset.inventory.profile == "generic"
    assert dataset.inventory.total_messages == 3
    assert [stream.key for stream in dataset.inventory.streams] == ["/telemetry"]


def test_discovers_ros2_profile_and_bag_directory(ros2_mcap_factory):
    path = ros2_mcap_factory()
    assert resolve_mcap_source(path.parent) == path
    inventory = inspect_dataset(path.parent)
    assert inventory.profile == "ros2"
    assert inventory.total_messages == 3
    assert inventory.streams[0].dtype == "sensor_msgs/msg/JointState"


def test_rejects_ambiguous_mcap_directory(mcap_factory):
    first = mcap_factory()
    second = mcap_factory()
    assert first.parent == second.parent
    with pytest.raises(AdapterError, match="multiple MCAP files"):
        discover(first.parent)


def test_ros2_db3_has_conversion_guidance(tmp_path: Path):
    path = tmp_path / "recording.db3"
    path.write_bytes(b"SQLite format 3\x00")
    with pytest.raises(AdapterError, match="ros2 bag convert"):
        discover(path)


def test_profile_can_be_forced_to_generic(ros2_mcap_factory):
    dataset = discover(ros2_mcap_factory(), profile="generic")
    assert dataset.inventory.profile == "generic"
    assert "ros2" not in dataset.inventory.capabilities


def test_timing_observations_are_bounded(mcap_factory):
    timestamps = [1_000_000_000 + index * 10_000_000 for index in range(5_000)]
    dataset = discover(mcap_factory(log_times_ns=timestamps))
    channel = next(iter(dataset.scan().channels.values()))
    assert channel.message_count == 5_000
    assert len(channel.positive_log_intervals_ns) == 4_096
