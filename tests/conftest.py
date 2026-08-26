from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import pytest


@pytest.fixture
def dataset_factory(tmp_path: Path):
    counter = 0

    def make(
        *,
        timestamps: list[float] | None = None,
        states: list[list[float] | None] | None = None,
        actions: list[list[float] | None] | None = None,
        episode_lengths: tuple[int, int] = (6, 6),
        declared_state_shape: tuple[int, ...] = (2,),
        include_action_declaration: bool = True,
        include_video: bool = False,
        video_mode: str = "clean",
        fps: float = 30,
        repo_id: str | None = "tests/fixture",
    ) -> Path:
        nonlocal counter
        counter += 1
        root = tmp_path / f"dataset-{counter}"
        (root / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
        (root / "data" / "chunk-000").mkdir(parents=True)
        total = sum(episode_lengths)
        if timestamps is None:
            timestamps = [i / fps for length in episode_lengths for i in range(length)]
        if states is None:
            states = [[float(i), float(i + 1)] for i in range(total)]
        if actions is None:
            actions = [[float(i) / 10, float(i + 1) / 10] for i in range(total)]
        features: dict[str, Any] = {
            "timestamp": {"dtype": "float64", "shape": [1]},
            "frame_index": {"dtype": "int64", "shape": [1]},
            "episode_index": {"dtype": "int64", "shape": [1]},
            "index": {"dtype": "int64", "shape": [1]},
            "observation.state": {
                "dtype": "float32",
                "shape": list(declared_state_shape),
                "names": ["joint_0", "joint_1"],
            },
        }
        if include_action_declaration:
            features["action"] = {
                "dtype": "float32",
                "shape": [2],
                "names": ["joint_0", "joint_1"],
            }
        if include_video:
            features["observation.images.wrist"] = {
                "dtype": "video",
                "shape": [48, 64, 3],
            }
        info = {
            "codebase_version": "v3.0",
            "robot_type": "testbot",
            "fps": fps,
            "total_episodes": 2,
            "total_frames": total,
            "features": features,
            "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        }
        if repo_id is not None:
            info["repo_id"] = repo_id
        if include_video:
            info["video_path"] = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
        (root / "meta" / "info.json").write_text(json.dumps(info), encoding="utf-8")

        episode_index = [index for index, length in enumerate(episode_lengths) for _ in range(length)]
        frame_index = [frame for length in episode_lengths for frame in range(length)]
        data = {
            "timestamp": pa.array(timestamps, type=pa.float64()),
            "frame_index": pa.array(frame_index, type=pa.int64()),
            "episode_index": pa.array(episode_index, type=pa.int64()),
            "index": pa.array(range(total), type=pa.int64()),
            "observation.state": pa.array(states, type=pa.list_(pa.float32(), 2)),
            "action": pa.array(
                actions,
                type=pa.list_(pa.float32()) if any(value is None for value in actions) else pa.list_(pa.float32(), 2),
            ),
        }
        pq.write_table(pa.table(data), root / "data" / "chunk-000" / "file-000.parquet")

        first_length, second_length = episode_lengths
        episodes: dict[str, Any] = {
            "episode_index": [0, 1],
            "length": list(episode_lengths),
            "tasks": [["test task"], ["test task"]],
            "data/chunk_index": [0, 0],
            "data/file_index": [0, 0],
            "dataset_from_index": [0, first_length],
            "dataset_to_index": [first_length, first_length + second_length],
            "meta/episodes/chunk_index": [0, 0],
            "meta/episodes/file_index": [0, 0],
        }
        if include_video:
            stream = "videos/observation.images.wrist"
            episodes.update(
                {
                    f"{stream}/chunk_index": [0, 0],
                    f"{stream}/file_index": [0, 0],
                    f"{stream}/from_timestamp": [0.0, first_length / fps],
                    f"{stream}/to_timestamp": [first_length / fps, total / fps],
                }
            )
            _write_video(root, total, video_mode, first_length, fps)
        pq.write_table(
            pa.Table.from_pydict(episodes),
            root / "meta" / "episodes" / "chunk-000" / "file-000.parquet",
        )
        return root

    return make


def _write_video(root: Path, total: int, mode: str, first_length: int, fps: float) -> None:
    cv2 = pytest.importorskip("cv2")
    path = root / "videos" / "observation.images.wrist" / "chunk-000" / "file-000.mp4"
    path.parent.mkdir(parents=True)
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (64, 48))
    assert writer.isOpened()
    for index in range(total):
        if mode == "frozen":
            intensity = 100
        elif mode == "black" and index >= first_length:
            intensity = 0
        else:
            intensity = 20 + index * 12
        image = np.full((48, 64, 3), intensity, dtype=np.uint8)
        image[:, index % 64, :] = min(255, intensity + 10)
        writer.write(image)
    writer.release()
