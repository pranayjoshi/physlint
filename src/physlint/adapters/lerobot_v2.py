"""LeRobot v2.0/v2.1 per-episode Parquet and video layout.

Format reference: huggingface/lerobot v0.3.3, datasets/utils.py and
datasets/lerobot_dataset.py. Statistics are not required by integrity rules.
"""

from __future__ import annotations

import json

from physlint.adapters.base import AdapterError
from physlint.adapters.lerobot import LeRobotAdapter
from physlint.models.dataset import Episode

DATA_PATH = "data/chunk-{episode_chunk:03d}/episode_{episode_index:06d}.parquet"
VIDEO_PATH = "videos/chunk-{episode_chunk:03d}/{video_key}/episode_{episode_index:06d}.mp4"


class LeRobotV2Adapter(LeRobotAdapter):
    """Reuse lazy numeric and video analysis with explicit v2 episode locators."""

    version_pattern = r"v2\.[01]"
    version_label = "v2.0 or v2.1"

    def _read_episodes(self) -> list[Episode]:
        path = self.root / "meta" / "episodes.jsonl"
        try:
            with path.open(encoding="utf-8") as source:
                records = [json.loads(line) for line in source if line.strip()]
        except (OSError, ValueError) as exc:
            raise AdapterError(f"cannot read LeRobot v2 episodes.jsonl: {exc}") from exc
        if not records or any(not isinstance(record, dict) for record in records):
            raise AdapterError("LeRobot v2 episodes.jsonl must contain episode objects")
        try:
            chunks_size = int(self._info.get("chunks_size", 1000))
            if chunks_size <= 0:
                raise ValueError("chunks_size must be positive")
            records.sort(key=lambda record: int(record["episode_index"]))
            episodes: list[Episode] = []
            offset = 0
            for record in records:
                index, length = int(record["episode_index"]), int(record["length"])
                if index < 0:
                    raise ValueError("episode_index must be nonnegative")
                values = {"episode_chunk": index // chunks_size, "episode_index": index}
                video_files = {
                    stream.key: self._format_path(
                        str(self._info.get("video_path") or VIDEO_PATH), video_key=stream.key, **values
                    )
                    for stream in self._features
                    if stream.kind == "video"
                }
                tasks = record.get("tasks") or []
                if isinstance(tasks, str):
                    tasks = [tasks]
                episodes.append(
                    Episode(
                        index=index,
                        identifier=f"episode_{index:06d}",
                        length=length,
                        data_file=self._format_path(str(self._info.get("data_path") or DATA_PATH), **values),
                        from_index=offset,
                        to_index=offset + length,
                        tasks=[str(task) for task in tasks],
                        video_files=video_files,
                        video_ranges={key: (0.0, length / float(self._info["fps"])) for key in video_files},
                    )
                )
                offset += length
            return episodes
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            raise AdapterError(f"invalid LeRobot v2 episode metadata: {exc}") from exc
