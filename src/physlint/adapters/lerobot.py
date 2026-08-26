"""A dependency-light, read-only adapter for local LeRobot Dataset v3.0."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from physlint.adapters.base import AdapterError
from physlint.models.dataset import (
    DatasetInventory,
    Episode,
    SampleBatch,
    Stream,
    VideoAnalysis,
    VideoFrame,
)

DEFAULT_DATA_PATH = "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"
DEFAULT_VIDEO_PATH = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"


class LeRobotAdapter:
    """Expose LeRobot v3 metadata and samples through the canonical lazy view."""

    name = "lerobot"
    version = "3.0"

    def __init__(self, root: Path):
        self.root = root
        self._info = self._read_info()
        self._features = self._read_features()
        self._episodes = self._read_episodes()
        self._schema_cache: dict[Path, pa.Schema] = {}
        self._video_analysis_cache: dict[tuple[int, str], VideoAnalysis] = {}
        inferred_name, source_revision = _hugging_face_identity(root)
        capabilities = {"metadata", "episodes", "timestamps", "numeric"}
        if any(stream.kind == "video" for stream in self._features):
            capabilities.add("video")
        if any(stream.key.endswith(".timestamp") for stream in self._features):
            capabilities.add("stream_timestamps")
        self.inventory = DatasetInventory(
            name=str(self._info.get("repo_id") or inferred_name or root.name),
            source_revision=source_revision,
            path=str(root),
            adapter=self.name,
            format_version=str(self._info.get("codebase_version", "unknown")),
            robot_type=self._info.get("robot_type"),
            fps=float(self._info["fps"]),
            total_frames=int(self._info.get("total_frames", sum(ep.length for ep in self._episodes))),
            streams=self._features,
            episodes=self._episodes,
            capabilities=frozenset(capabilities),
        )

    def _read_info(self) -> dict[str, Any]:
        path = self.root / "meta" / "info.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise AdapterError(f"missing LeRobot metadata: {path}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise AdapterError(f"unreadable LeRobot metadata {path}: {exc}") from exc
        if not isinstance(payload, dict):
            raise AdapterError(f"LeRobot info must be an object: {path}")
        version = str(payload.get("codebase_version", ""))
        if not version.startswith("v3"):
            raise AdapterError(f"unsupported LeRobot version {version or 'missing'}; Physlint supports v3.x")
        if not isinstance(payload.get("features"), dict) or "fps" not in payload:
            raise AdapterError("LeRobot info.json is missing features or fps")
        return payload

    def _read_features(self) -> list[Stream]:
        streams: list[Stream] = []
        for key, raw in self._info["features"].items():
            if not isinstance(raw, dict):
                raise AdapterError(f"feature declaration for {key!r} must be an object")
            dtype = str(raw.get("dtype", "unknown"))
            shape = tuple(int(value) for value in raw.get("shape", ()))
            kind = "video" if dtype == "video" else "image" if dtype == "image" else "numeric"
            streams.append(
                Stream(
                    key=key,
                    dtype=dtype,
                    shape=shape,
                    kind=kind,
                    names=raw.get("names"),
                    units=raw.get("unit") or raw.get("units"),
                )
            )
        return streams

    def _read_episodes(self) -> list[Episode]:
        paths = sorted((self.root / "meta" / "episodes").glob("**/*.parquet"))
        if not paths:
            raise AdapterError("missing LeRobot v3 episode metadata parquet files")
        records: list[dict[str, Any]] = []
        try:
            for path in paths:
                table = pq.read_table(path)
                records.extend(table.to_pylist())
        except (OSError, pa.ArrowException) as exc:
            if "Repetition level histogram size mismatch" in str(exc):
                raise AdapterError(
                    "cannot read episode metadata because PyArrow 19.0.0 has a Parquet repetition-level "
                    "reader bug; upgrade PyArrow to >=19.0.1 and rerun the validation"
                ) from exc
            raise AdapterError(f"cannot read episode metadata: {exc}") from exc
        episodes = [self._episode_from_record(record) for record in records]
        return sorted(episodes, key=lambda episode: episode.index)

    def _episode_from_record(self, record: dict[str, Any]) -> Episode:
        try:
            index = int(record["episode_index"])
            length = int(record["length"])
        except (KeyError, TypeError, ValueError) as exc:
            raise AdapterError("episode metadata lacks a valid episode_index or length") from exc
        data_file: str | None = None
        if "data/chunk_index" in record and "data/file_index" in record:
            data_file = self._format_path(
                str(self._info.get("data_path", DEFAULT_DATA_PATH)),
                chunk_index=int(record["data/chunk_index"]),
                file_index=int(record["data/file_index"]),
            )
        video_files: dict[str, str] = {}
        video_ranges: dict[str, tuple[float, float]] = {}
        for stream in self._features:
            if stream.kind != "video":
                continue
            prefix = f"videos/{stream.key}"
            if f"{prefix}/chunk_index" in record and f"{prefix}/file_index" in record:
                video_files[stream.key] = self._format_path(
                    str(self._info.get("video_path", DEFAULT_VIDEO_PATH)),
                    video_key=stream.key,
                    chunk_index=int(record[f"{prefix}/chunk_index"]),
                    file_index=int(record[f"{prefix}/file_index"]),
                )
                start = float(record.get(f"{prefix}/from_timestamp", 0.0))
                end = float(record.get(f"{prefix}/to_timestamp", start + length / self._info["fps"]))
                video_ranges[stream.key] = (start, end)
        tasks = record.get("tasks") or []
        if isinstance(tasks, str):
            tasks = [tasks]
        return Episode(
            index=index,
            identifier=str(record.get("episode_id", f"episode_{index:06d}")),
            length=length,
            data_file=data_file,
            from_index=_optional_int(record.get("dataset_from_index")),
            to_index=_optional_int(record.get("dataset_to_index")),
            tasks=[str(task) for task in tasks],
            video_files=video_files,
            video_ranges=video_ranges,
        )

    @staticmethod
    def _format_path(template: str, **values: Any) -> str:
        try:
            return template.format(**values)
        except (KeyError, ValueError) as exc:
            raise AdapterError(f"invalid path template in info.json: {template}") from exc

    def _data_path(self, episode: Episode) -> Path:
        if episode.data_file is None:
            raise AdapterError(f"episode {episode.identifier} has no data-file reference")
        path = self.root / episode.data_file
        if not path.is_file():
            raise AdapterError(f"episode data file is missing: {path}")
        return path

    def parquet_schema(self, episode: Episode) -> dict[str, Any]:
        path = self._data_path(episode)
        if path not in self._schema_cache:
            try:
                self._schema_cache[path] = pq.read_schema(path)
            except (OSError, pa.ArrowException) as exc:
                raise AdapterError(f"cannot read parquet schema {path}: {exc}") from exc
        return {field.name: field.type for field in self._schema_cache[path]}

    def iter_batches(
        self,
        episode: Episode,
        columns: tuple[str, ...] | None = None,
        batch_size: int = 65_536,
    ) -> Iterator[SampleBatch]:
        path = self._data_path(episode)
        try:
            parquet = pq.ParquetFile(path)
            available = set(parquet.schema_arrow.names)
            requested = list(columns or tuple(available))
            selector = "episode_index" if "episode_index" in available else "index"
            read_columns = list(dict.fromkeys([*requested, selector]))
            missing = set(read_columns) - available
            if missing:
                raise AdapterError(f"columns missing from {path}: {', '.join(sorted(missing))}")
            for raw in parquet.iter_batches(batch_size=batch_size, columns=read_columns):
                selection = raw.column(raw.schema.get_field_index(selector)).to_numpy(zero_copy_only=False)
                if selector == "episode_index":
                    mask = selection == episode.index
                elif episode.from_index is not None and episode.to_index is not None:
                    mask = (selection >= episode.from_index) & (selection < episode.to_index)
                else:
                    mask = np.ones(len(selection), dtype=bool)
                if not np.any(mask):
                    continue
                converted: dict[str, np.ndarray] = {}
                for name in requested:
                    array = raw.column(raw.schema.get_field_index(name))
                    converted[name] = _arrow_to_numpy(array)[mask]
                yield SampleBatch(episode=episode, columns=converted)
        except AdapterError:
            raise
        except (OSError, pa.ArrowException) as exc:
            raise AdapterError(f"cannot stream parquet data {path}: {exc}") from exc

    def iter_video_frames(self, episode: Episode, stream: str, stride: int = 1) -> Iterator[VideoFrame]:
        try:
            import cv2
        except ImportError as exc:  # pragma: no cover - environment dependent
            raise AdapterError("video checks require the 'video' optional dependency") from exc
        if stream not in episode.video_files:
            raise AdapterError(f"episode {episode.identifier} has no {stream} video reference")
        path = self.root / episode.video_files[stream]
        capture = cv2.VideoCapture(str(path))
        if not capture.isOpened():
            capture.release()
            raise AdapterError(f"cannot decode video: {path}")
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or self.inventory.fps
        start, end = episode.video_ranges.get(stream, (0.0, episode.length / fps))
        start_frame = max(0, int(round(start * fps)))
        end_frame = max(start_frame, int(round(end * fps)))
        capture.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
        try:
            for frame_index in range(start_frame, end_frame):
                ok, image = capture.read()
                if not ok:
                    break
                relative = frame_index - start_frame
                if relative % max(1, stride):
                    continue
                yield VideoFrame(
                    episode=episode,
                    stream=stream,
                    frame_index=relative,
                    timestamp=relative / fps,
                    image=image,
                )
        finally:
            capture.release()

    def video_analysis(self, episode: Episode, stream: str) -> VideoAnalysis:
        """Decode once and cache small, non-image statistics for every video rule."""
        key = (episode.index, stream)
        cached = self._video_analysis_cache.get(key)
        if cached is not None:
            return cached

        frame_indices: list[int] = []
        timestamps: list[float] = []
        means: list[float] = []
        stddevs: list[float] = []
        differences: list[float] = []
        previous: np.ndarray | None = None
        for frame in self.iter_video_frames(episode, stream):
            small = _small_grayscale(frame.image)
            frame_indices.append(frame.frame_index)
            timestamps.append(frame.timestamp)
            means.append(float(np.mean(small)))
            stddevs.append(float(np.std(small)))
            if previous is not None:
                differences.append(float(np.mean(np.abs(small - previous))))
            previous = small
        analysis = VideoAnalysis(
            frame_indices=np.asarray(frame_indices, dtype=np.int64),
            timestamps=np.asarray(timestamps, dtype=float),
            mean_intensities=np.asarray(means, dtype=float),
            stddevs=np.asarray(stddevs, dtype=float),
            mean_absolute_differences=np.asarray(differences, dtype=float),
        )
        self._video_analysis_cache[key] = analysis
        return analysis


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _small_grayscale(image: np.ndarray) -> np.ndarray:
    """Spatially sample first, avoiding full-resolution color reductions."""
    row_stride = max(1, image.shape[0] // 64)
    col_stride = max(1, image.shape[1] // 64)
    small = image[::row_stride, ::col_stride]
    gray = np.mean(small, axis=2) if small.ndim == 3 else small
    return np.asarray(gray, dtype=np.float32)


def _hugging_face_identity(root: Path) -> tuple[str | None, str | None]:
    """Recover repo/revision from a Hugging Face snapshot cache path."""
    parts = root.resolve().parts
    for index, part in enumerate(parts):
        if not part.startswith("datasets--") or index + 2 >= len(parts):
            continue
        if parts[index + 1] != "snapshots":
            continue
        encoded = part.removeprefix("datasets--")
        namespace, separator, repository = encoded.partition("--")
        if separator and namespace and repository:
            return f"{namespace}/{repository}", parts[index + 2]
    return None, None


def _arrow_to_numpy(array: pa.Array) -> np.ndarray:
    """Preserve vector columns as a dense array when their shape is regular."""
    values = array.to_pylist()
    try:
        return np.asarray(values)
    except ValueError:
        return np.asarray(values, dtype=object)
