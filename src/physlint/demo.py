"""Small deterministic datasets for the zero-setup product demo."""

from __future__ import annotations

import json
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def write_demo_dataset(root: Path, *, corrupted: bool) -> Path:
    """Write a minimal LeRobot v3 dataset, optionally with one NaN action."""
    (root / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
    (root / "data" / "chunk-000").mkdir(parents=True)
    length = 8
    features = {
        "timestamp": {"dtype": "float64", "shape": [1]},
        "frame_index": {"dtype": "int64", "shape": [1]},
        "episode_index": {"dtype": "int64", "shape": [1]},
        "index": {"dtype": "int64", "shape": [1]},
        "observation.state": {
            "dtype": "float32",
            "shape": [2],
            "names": ["joint_0", "joint_1"],
        },
        "action": {
            "dtype": "float32",
            "shape": [2],
            "names": ["joint_0", "joint_1"],
        },
    }
    info = {
        "codebase_version": "v3.0",
        "repo_id": "physlint/demo-corrupted" if corrupted else "physlint/demo-clean",
        "robot_type": "demo-arm",
        "fps": 20,
        "total_episodes": 1,
        "total_frames": length,
        "features": features,
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
    }
    (root / "meta" / "info.json").write_text(json.dumps(info), encoding="utf-8")

    actions = [[index / 10, (index + 1) / 10] for index in range(length)]
    if corrupted:
        actions[4][0] = float("nan")
    samples = pa.table(
        {
            "timestamp": pa.array([index / 20 for index in range(length)], type=pa.float64()),
            "frame_index": pa.array(range(length), type=pa.int64()),
            "episode_index": pa.array([0] * length, type=pa.int64()),
            "index": pa.array(range(length), type=pa.int64()),
            "observation.state": pa.array(
                [[float(index), float(index + 1)] for index in range(length)],
                type=pa.list_(pa.float32(), 2),
            ),
            "action": pa.array(actions, type=pa.list_(pa.float32(), 2)),
        }
    )
    pq.write_table(samples, root / "data" / "chunk-000" / "file-000.parquet")
    episodes = pa.table(
        {
            "episode_index": [0],
            "length": [length],
            "tasks": [["move the demo arm"]],
            "data/chunk_index": [0],
            "data/file_index": [0],
            "dataset_from_index": [0],
            "dataset_to_index": [length],
            "meta/episodes/chunk_index": [0],
            "meta/episodes/file_index": [0],
        }
    )
    pq.write_table(episodes, root / "meta" / "episodes" / "chunk-000" / "file-000.parquet")
    return root
