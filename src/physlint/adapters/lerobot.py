"""A dependency-light, read-only adapter for local LeRobot Dataset v3.0."""

from __future__ import annotations

import json
import math
import re
from collections import OrderedDict
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pydantic import ValidationError

from physlint.adapters.base import AdapterError
from physlint.models.dataset import (
    DatasetInventory,
    Episode,
    SampleBatch,
    Stream,
    VideoAnalysis,
    VideoFrame,
    VideoProbe,
)

DEFAULT_DATA_PATH = "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet"
DEFAULT_VIDEO_PATH = "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4"
COLUMN_CACHE_BYTES = 512 * 1024 * 1024


class LeRobotAdapter:
    """Expose LeRobot v3 metadata and samples through the canonical lazy view."""

    name = "lerobot"
    version = "3.0"
    version_pattern = r"v3\.\d+"
    version_label = "v3.x"

    def __init__(self, root: Path):
        self.root = root
        self._info = self._read_info()
        self.version = str(self._info["codebase_version"]).removeprefix("v")
        self._features = self._read_features()
        self._episodes = self._read_episodes()
        self._schema_cache: dict[Path, pa.Schema] = {}
        self._column_cache: OrderedDict[tuple[Path, str], tuple[np.ndarray, int]] = OrderedDict()
        self._column_cache_bytes = 0
        self._episode_rows: dict[Path, dict[int, np.ndarray]] = {}
        self._column_sizes: dict[Path, dict[str, int]] = {}
        self._video_probes: dict[str, VideoProbe] = {}
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
        if not re.fullmatch(self.version_pattern, version):
            raise AdapterError(f"unsupported LeRobot version {version or 'missing'}; expected {self.version_label}")
        if not isinstance(payload.get("features"), dict) or "fps" not in payload:
            raise AdapterError("LeRobot info.json is missing features or fps")
        try:
            if not math.isfinite(float(payload["fps"])) or float(payload["fps"]) <= 0:
                raise ValueError("fps must be finite and positive")
        except (TypeError, ValueError) as exc:
            raise AdapterError("LeRobot fps must be finite and positive") from exc
        return payload

    def _read_features(self) -> list[Stream]:
        streams: list[Stream] = []
        for key, raw in self._info["features"].items():
            if not isinstance(raw, dict):
                raise AdapterError(f"feature declaration for {key!r} must be an object")
            dtype = str(raw.get("dtype", "unknown"))
            shape = tuple(int(value) for value in raw.get("shape", ()))
            kind = "video" if dtype == "video" else "image" if dtype == "image" else "numeric"
            try:
                streams.append(
                    Stream(
                        key=key,
                        dtype=dtype,
                        shape=shape,
                        kind=kind,
                        names=_normalize_feature_names(raw.get("names")),
                        units=raw.get("unit") or raw.get("units"),
                    )
                )
            except ValidationError as exc:
                raise AdapterError(f"invalid LeRobot feature declaration for {key!r}") from exc
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
            sizes = self._column_sizes.get(path)
            if sizes is None:
                sizes = self._column_sizes[path] = _uncompressed_column_sizes(parquet)
            if all(sizes.get(name, 0) <= COLUMN_CACHE_BYTES for name in read_columns):
                rows = self._rows_for_episode(parquet, path, selector, episode)
                loaded = {name: self._column(parquet, path, name, sizes.get(name, 0)) for name in requested}
                for start in range(0, rows.size, batch_size):
                    selected = rows[start : start + batch_size]
                    yield SampleBatch(episode=episode, columns={name: loaded[name][selected] for name in requested})
                return
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

    def _column(self, parquet: pq.ParquetFile, path: Path, name: str, cost: int) -> np.ndarray:
        """Decode a shared-file column once so per-episode reads stay linear in file size."""
        key = (path, name)
        cached = self._column_cache.get(key)
        if cached is not None:
            self._column_cache.move_to_end(key)
            return cached[0]
        try:
            table = parquet.read(columns=[name])
        except pa.ArrowInvalid as exc:
            if "Expected all lists to be of size" in str(exc):
                raise AdapterError(
                    f"column {name} in {path.name} has null or short rows in a fixed-size list, "
                    "which PyArrow and LeRobot cannot read; re-export the affected episodes"
                ) from exc
            raise
        values = _arrow_to_numpy(table.column(0))
        self._column_cache[key] = (values, cost)
        self._column_cache_bytes += cost
        while self._column_cache_bytes > COLUMN_CACHE_BYTES and len(self._column_cache) > 1:
            _, (_, evicted) = self._column_cache.popitem(last=False)
            self._column_cache_bytes -= evicted
        return values

    def _rows_for_episode(self, parquet: pq.ParquetFile, path: Path, selector: str, episode: Episode) -> np.ndarray:
        if selector == "episode_index":
            lookup = self._episode_rows.get(path)
            if lookup is None:
                values = _arrow_to_numpy(parquet.read(columns=[selector]).column(0))
                order = np.argsort(values, kind="stable")
                labels, starts = np.unique(values[order], return_index=True)
                lookup = dict(zip(labels.tolist(), np.split(order, starts[1:]), strict=True)) if labels.size else {}
                self._episode_rows[path] = lookup
            return lookup.get(episode.index, np.empty(0, dtype=np.int64))
        total = parquet.metadata.num_rows
        if episode.from_index is None or episode.to_index is None:
            return np.arange(total)
        values = _arrow_to_numpy(parquet.read(columns=[selector]).column(0))
        return np.flatnonzero((values >= episode.from_index) & (values < episode.to_index))

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
        fps = float(capture.get(cv2.CAP_PROP_FPS)) or float(self._info["fps"])
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

    def video_probe(self, relative_path: str) -> VideoProbe | None:
        """Decode a video once with PyAV, whose errors OpenCV hides; None when PyAV is unavailable."""
        cached = self._video_probes.get(relative_path)
        if cached is not None:
            return cached
        try:
            import av
        except ImportError:  # pragma: no cover - environment dependent
            return None
        times: list[float] = []
        errors = 0
        first_error: float | None = None
        fps: float | None = None
        try:
            with av.logging.Capture(True) as logs, av.open(str(self.root / relative_path)) as container:
                video = container.streams.video[0]
                video.thread_type = "AUTO"
                fps = float(video.average_rate) if video.average_rate else None
                for packet in container.demux(video):
                    try:
                        for frame in video.decode(packet):
                            if frame.pts is not None and frame.time_base is not None:
                                times.append(float(frame.pts * frame.time_base))
                    except av.error.FFmpegError:
                        errors += 1
                        if first_error is None and packet.pts is not None and packet.time_base is not None:
                            first_error = float(packet.pts * packet.time_base)
            errors += sum(1 for level, _name, _message in logs if level <= av.logging.ERROR)
        except (OSError, av.error.FFmpegError, IndexError) as exc:
            raise AdapterError(f"cannot decode video {relative_path}: {exc}") from exc
        probe = VideoProbe(np.sort(np.asarray(times, dtype=float)), errors, first_error, fps)
        self._video_probes[relative_path] = probe
        return probe

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
        cell_differences: list[float] = []
        previous: np.ndarray | None = None
        total: np.ndarray | None = None
        for frame in self.iter_video_frames(episode, stream):
            small = _small_grayscale(frame.image)
            frame_indices.append(frame.frame_index)
            timestamps.append(frame.timestamp)
            means.append(float(np.mean(small)))
            stddevs.append(float(np.std(small)))
            if previous is not None:
                change = np.abs(small - previous)
                differences.append(float(np.mean(change)))
                cell_differences.append(float(np.max(change)))
            previous = small
            total = small.copy() if total is None else total + small
        analysis = VideoAnalysis(
            frame_indices=np.asarray(frame_indices, dtype=np.int64),
            timestamps=np.asarray(timestamps, dtype=float),
            mean_intensities=np.asarray(means, dtype=float),
            stddevs=np.asarray(stddevs, dtype=float),
            mean_absolute_differences=np.asarray(differences, dtype=float),
            max_cell_differences=np.asarray(cell_differences, dtype=float),
            mean_frame=np.zeros(0) if total is None else total / len(frame_indices),
        )
        self._video_analysis_cache[key] = analysis
        return analysis


def _normalize_feature_names(value: Any) -> list[str] | dict[str, list[str]] | None:
    """Accept Hub layouts that store a single name as a string."""
    if value is None or isinstance(value, dict):
        return value
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    raise AdapterError(f"feature names must be a string, list, or object, not {type(value).__name__}")


def _optional_int(value: Any) -> int | None:
    return None if value is None else int(value)


def _small_grayscale(image: np.ndarray) -> np.ndarray:
    """Average into a small grid: unlike point sampling, small moving objects still register."""
    import cv2

    gray = np.asarray(np.mean(image, axis=2) if image.ndim == 3 else image, dtype=np.float32)
    width = min(64, gray.shape[1])
    height = max(1, round(gray.shape[0] * width / gray.shape[1]))
    return np.asarray(cv2.resize(gray, (width, height), interpolation=cv2.INTER_AREA), dtype=np.float32)


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


def _uncompressed_column_sizes(parquet: pq.ParquetFile) -> dict[str, int]:
    sizes: dict[str, int] = {}
    metadata = parquet.metadata
    fields = parquet.schema_arrow.names
    for group in range(metadata.num_row_groups):
        row_group = metadata.row_group(group)
        for index in range(row_group.num_columns):
            column = row_group.column(index)
            name = column.path_in_schema
            top_level = next(
                (field for field in fields if name == field or name.startswith(f"{field}.")),
                name,
            )
            sizes[top_level] = sizes.get(top_level, 0) + int(column.total_uncompressed_size)
    return sizes


def _dense_numpy(array: pa.Array) -> np.ndarray | None:
    """Convert null-free numeric scalars and regular nested lists without Python objects."""
    if array.null_count:
        return None
    kind = array.type
    if pa.types.is_floating(kind) or pa.types.is_integer(kind) or pa.types.is_boolean(kind):
        return np.asarray(array.to_numpy(zero_copy_only=False))
    if pa.types.is_fixed_size_list(kind):
        width = int(kind.list_size)
    elif pa.types.is_list(kind) or pa.types.is_large_list(kind):
        lengths = np.asarray(pc.list_value_length(array).to_numpy(zero_copy_only=False))
        if lengths.size == 0 or np.any(lengths != lengths[0]):
            return None
        width = int(lengths[0])
    else:
        return None
    inner = _dense_numpy(array.flatten())
    if inner is None or width == 0:
        return None
    return inner.reshape((len(array), width, *inner.shape[1:]))


def _arrow_to_numpy(array: pa.Array | pa.ChunkedArray) -> np.ndarray:
    """Preserve vector columns as a dense array when their shape is regular."""
    if isinstance(array, pa.ChunkedArray):
        array = array.chunk(0) if array.num_chunks == 1 else pa.concat_arrays(array.chunks)
    dense = _dense_numpy(array)
    if dense is not None:
        return dense
    values = array.to_pylist()
    try:
        return np.asarray(values)
    except ValueError:
        return np.asarray(values, dtype=object)
