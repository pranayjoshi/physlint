"""Measure defect detection and false alarms with controlled, reproducible corruptions.

Every trial links a source dataset into a scratch workspace, replaces only the files a
recipe changes, and compares the Default-contract findings against a clean baseline.
Source datasets are never written to.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import shutil
from collections.abc import Callable, Iterable
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from physlint.config import CacheSettings, Config, RuleSettings
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.dataset import Episode
from physlint.models.finding import Report, RuleStatus, Severity
from physlint.rules import BUILTIN_RULES

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "benchmark_manifest.yaml"
DEFAULT_OUTPUT = ROOT / "reports" / "corruption-benchmark-2026-10-31-v2"
DEFAULT_WORK = ROOT / ".work" / "benchmark"
SURVEY_ROOT = ROOT / ".work" / "survey" / "datasets"
MAX_TRANSFORM_VIDEO_BYTES = 64 * 1024 * 1024
UNCAPPED_FINDINGS = 1_000_000
BLOCKING = {Severity.ERROR, Severity.CRITICAL}
FLOAT_STATES = ("observation.state", "action")


class RecipeSkipped(Exception):
    """The dataset cannot express this defect, for example one camera or one Parquet file."""


# ---------------------------------------------------------------------------
# Workspace and mutation helpers
# ---------------------------------------------------------------------------


def link_workspace(source: Path, destination: Path) -> None:
    """Mirror a dataset with file symlinks, so a replaced file never reaches the source."""
    if destination.exists():
        shutil.rmtree(destination)
    for directory, names, files in os.walk(source, followlinks=True):
        relative = Path(directory).relative_to(source)
        names[:] = [name for name in names if name != ".cache"]
        (destination / relative).mkdir(parents=True, exist_ok=True)
        for name in files:
            (destination / relative / name).symlink_to((Path(directory) / name).resolve())


def replace_bytes(path: Path, payload: bytes) -> None:
    path.unlink(missing_ok=True)
    path.write_bytes(payload)


def replace_parquet(path: Path, table: pa.Table, **options: Any) -> None:
    path.unlink(missing_ok=True)
    pq.write_table(table, path, **options)


@dataclass
class Context:
    root: Path
    episodes: list[Episode]
    episode: Episode
    rng: np.random.Generator
    fps: float
    video_streams: list[str]
    targets: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        self.targets = {self.episode.identifier}

    @property
    def data_path(self) -> Path:
        if self.episode.data_file is None:
            raise RecipeSkipped("episode has no data file")
        return self.root / self.episode.data_file

    def load(self) -> tuple[pa.Table, np.ndarray]:
        table = pq.read_table(self.data_path)
        if "episode_index" not in table.schema.names:
            raise RecipeSkipped("samples have no episode_index")
        rows = np.flatnonzero(table["episode_index"].to_numpy() == self.episode.index)
        if rows.size < 12:
            raise RecipeSkipped("target episode is too short")
        return table, rows

    def stream_values(self, table: pa.Table, stream: str) -> list[Any]:
        if stream not in table.schema.names:
            raise RecipeSkipped(f"dataset has no {stream} column")
        return table[stream].to_pylist()

    def store(self, table: pa.Table, stream: str, values: list[Any]) -> pa.Table:
        position = table.schema.get_field_index(stream)
        return table.set_column(
            position, table.schema.field(position), pa.array(values, type=table.schema.field(position).type)
        )

    def save(self, table: pa.Table) -> None:
        replace_parquet(self.data_path, table)

    def edit_info(self, change: Callable[[dict[str, Any]], None]) -> None:
        path = self.root / "meta" / "info.json"
        info = json.loads(path.read_text(encoding="utf-8"))
        change(info)
        replace_bytes(path, json.dumps(info).encode())

    def edit_episode_records(self, change: Callable[[list[dict[str, Any]]], None]) -> None:
        jsonl = self.root / "meta" / "episodes.jsonl"
        if jsonl.is_file():
            records = [json.loads(line) for line in jsonl.read_text(encoding="utf-8").splitlines() if line.strip()]
            change(records)
            replace_bytes(jsonl, "".join(json.dumps(item) + "\n" for item in records).encode())
            return
        for path in sorted((self.root / "meta" / "episodes").glob("**/*.parquet")):
            table = pq.read_table(path)
            records = table.to_pylist()
            before = json.dumps(records, sort_keys=True, default=str)
            change(records)
            if json.dumps(records, sort_keys=True, default=str) != before:
                replace_parquet(path, pa.Table.from_pylist(records, schema=table.schema))

    def video_path(self, stream: str | None = None) -> tuple[str, Path]:
        if not self.video_streams:
            raise RecipeSkipped("dataset has no video stream")
        chosen = stream or self.video_streams[0]
        if chosen not in self.episode.video_files:
            raise RecipeSkipped("episode has no video reference")
        relative = self.episode.video_files[chosen]
        self.targets |= {episode.identifier for episode in self.episodes if episode.video_files.get(chosen) == relative}
        path = self.root / relative
        if not path.is_file():
            raise RecipeSkipped("referenced video is missing")
        return chosen, path

    def rewrite_video(self, change: Callable[[int, int, int, np.ndarray], list[np.ndarray]]) -> None:
        """Re-encode one video; ``change`` receives file frame, episode start, episode end, and the frame."""
        import cv2

        stream, path = self.video_path()
        if path.stat().st_size > MAX_TRANSFORM_VIDEO_BYTES:
            raise RecipeSkipped("video file exceeds the re-encode budget")
        capture = cv2.VideoCapture(str(path))
        fps = capture.get(cv2.CAP_PROP_FPS) or self.fps
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
        start_time, end_time = self.episode.video_ranges.get(stream, (0.0, self.episode.length / fps))
        start, end = int(round(start_time * fps)), int(round(end_time * fps))
        temporary = path.with_name(f"{path.stem}.benchmark.mp4")
        writer = cv2.VideoWriter(str(temporary), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
        if not writer.isOpened():
            raise RecipeSkipped("mp4v encoder is unavailable")
        index = 0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            for output in change(index, start, end, frame):
                writer.write(output)
            index += 1
        capture.release()
        writer.release()
        path.unlink()
        temporary.replace(path)


@dataclass(frozen=True)
class Recipe:
    id: str
    category: str
    description: str
    apply: Callable[[Context, Any], None]
    levels: tuple[Any, ...] = (None,)
    touches_video: bool = False
    benign: bool = False
    needs_control: bool = False


RECIPES: dict[str, Recipe] = {}


def recipe(
    identifier: str,
    category: str,
    description: str,
    levels: tuple[Any, ...] = (None,),
    *,
    touches_video: bool = False,
    benign: bool = False,
    needs_control: bool = False,
) -> Callable[[Callable[[Context, Any], None]], Callable[[Context, Any], None]]:
    def register(function: Callable[[Context, Any], None]) -> Callable[[Context, Any], None]:
        RECIPES[identifier] = Recipe(
            identifier, category, description, function, levels, touches_video, benign, needs_control
        )
        return function

    return register


# ---------------------------------------------------------------------------
# Numeric defects
# ---------------------------------------------------------------------------


def _mutate_vectors(ctx: Context, stream: str, change: Callable[[np.ndarray], np.ndarray]) -> None:
    table, rows = ctx.load()
    values = ctx.stream_values(table, stream)
    matrix = np.asarray([values[row] for row in rows], dtype=float).reshape(len(rows), -1)
    updated = change(matrix.copy())
    for position, row in enumerate(rows):
        values[row] = updated[position].tolist()
    ctx.save(ctx.store(table, stream, values))


def _middle(ctx: Context, rows: int, count: int) -> np.ndarray:
    start = int(ctx.rng.integers(rows // 4, max(rows // 4 + 1, rows - rows // 4 - count)))
    return np.arange(start, min(rows, start + count))


@recipe("nan_action", "numeric", "NaN in action samples", (1, 10))
def nan_action(ctx: Context, count: int) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        matrix[_middle(ctx, len(matrix), count), 0] = np.nan
        return matrix

    _mutate_vectors(ctx, "action", change)


@recipe("inf_state", "numeric", "Infinity in observed state", (1, 10))
def inf_state(ctx: Context, count: int) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        matrix[_middle(ctx, len(matrix), count), 0] = np.inf
        return matrix

    _mutate_vectors(ctx, "observation.state", change)


@recipe("null_action_row", "numeric", "Null action row in the stored column")
def null_action_row(ctx: Context, _: Any) -> None:
    table, rows = ctx.load()
    values = ctx.stream_values(table, "action")
    values[int(rows[len(rows) // 2])] = None
    ctx.save(ctx.store(table, "action", values))


@recipe("action_spike", "numeric", "Single-sample action spike, in multiples of the stream range", (1.0, 10.0, 1000.0))
def action_spike(ctx: Context, scale: float) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        span = float(np.ptp(matrix[:, 0])) or 1.0
        matrix[_middle(ctx, len(matrix), 1), 0] += span * scale
        return matrix

    _mutate_vectors(ctx, "action", change)


@recipe("unit_flip", "numeric", "State changes from radians to degrees mid-episode")
def unit_flip(ctx: Context, _: Any) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        matrix[len(matrix) // 2 :] *= 57.2958
        return matrix

    _mutate_vectors(ctx, "observation.state", change)


@recipe("sign_flip_joint", "numeric", "One state joint changes sign mid-episode")
def sign_flip_joint(ctx: Context, _: Any) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        matrix[len(matrix) // 2 :, 0] *= -1
        return matrix

    _mutate_vectors(ctx, "observation.state", change)


@recipe("stuck_joint", "numeric", "One state joint is constant for the whole episode")
def stuck_joint(ctx: Context, _: Any) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        matrix[:, 0] = matrix[0, 0]
        return matrix

    _mutate_vectors(ctx, "observation.state", change)


@recipe("dead_action", "numeric", "Every action in the episode is exactly zero")
def dead_action(ctx: Context, _: Any) -> None:
    _mutate_vectors(ctx, "action", np.zeros_like)


@recipe("action_state_swap", "numeric", "Action and state columns are swapped in one episode")
def action_state_swap(ctx: Context, _: Any) -> None:
    table, rows = ctx.load()
    action = ctx.stream_values(table, "action")
    state = ctx.stream_values(table, "observation.state")
    if len(action[0]) != len(state[0]):
        raise RecipeSkipped("action and state dimensions differ")
    for row in rows:
        action[row], state[row] = state[row], action[row]
    ctx.save(ctx.store(ctx.store(table, "action", action), "observation.state", state))


@recipe("action_shift", "numeric", "Actions are rolled against observations by N frames", (1, 5, 30))
def action_shift(ctx: Context, frames: int) -> None:
    _mutate_vectors(ctx, "action", lambda matrix: np.roll(matrix, frames, axis=0))


@recipe("joint_permutation", "numeric", "Two state joints are swapped in one episode")
def joint_permutation(ctx: Context, _: Any) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        if matrix.shape[1] < 2:
            raise RecipeSkipped("state has one dimension")
        matrix[:, [0, 1]] = matrix[:, [1, 0]]
        return matrix

    _mutate_vectors(ctx, "observation.state", change)


@recipe("sensor_noise", "numeric", "Gaussian noise in multiples of each joint's standard deviation", (0.5, 5.0))
def sensor_noise(ctx: Context, scale: float) -> None:
    def change(matrix: np.ndarray) -> np.ndarray:
        return matrix + ctx.rng.normal(0, 1, matrix.shape) * matrix.std(axis=0, keepdims=True) * scale

    _mutate_vectors(ctx, "observation.state", change)


@recipe("exact_duplicate", "numeric", "One episode's numeric streams are copied into another")
def exact_duplicate(ctx: Context, _: Any) -> None:
    _copy_episode(ctx, 0.0)


@recipe("near_duplicate", "numeric", "One episode is copied with 1e-6 noise")
def near_duplicate(ctx: Context, _: Any) -> None:
    _copy_episode(ctx, 1e-6)


def _copy_episode(ctx: Context, noise: float) -> None:
    table, rows = ctx.load()
    labels = table["episode_index"].to_numpy()
    for other in ctx.episodes:
        if (
            other.index != ctx.episode.index
            and other.length == ctx.episode.length
            and other.data_file == ctx.episode.data_file
        ):
            source_rows = np.flatnonzero(labels == other.index)
            ctx.targets.add(other.identifier)
            break
    else:
        raise RecipeSkipped("no same-length episode in the same file")
    for stream in table.schema.names:
        kind = table.schema.field(stream).type
        is_vector = pa.types.is_list(kind) or pa.types.is_fixed_size_list(kind) or pa.types.is_large_list(kind)
        if not is_vector or not pa.types.is_floating(kind.value_type):
            continue
        values = table[stream].to_pylist()
        for source, destination in zip(source_rows, rows, strict=True):
            row = np.asarray(values[source], dtype=float)
            values[destination] = (row + ctx.rng.normal(0, noise, row.shape) if noise else row).tolist()
        table = ctx.store(table, stream, values)
    ctx.save(table)


# ---------------------------------------------------------------------------
# Temporal defects
# ---------------------------------------------------------------------------


def _mutate_timestamps(ctx: Context, change: Callable[[np.ndarray], np.ndarray]) -> None:
    table, rows = ctx.load()
    values = np.asarray(ctx.stream_values(table, "timestamp"), dtype=float)
    values[rows] = change(values[rows].copy())
    ctx.save(ctx.store(table, "timestamp", values.tolist()))


@recipe("nan_timestamp", "temporal", "NaN timestamps", (1, 10))
def nan_timestamp(ctx: Context, count: int) -> None:
    def change(values: np.ndarray) -> np.ndarray:
        values[_middle(ctx, len(values), count)] = np.nan
        return values

    _mutate_timestamps(ctx, change)


@recipe("swapped_timestamps", "temporal", "Two adjacent timestamps are swapped")
def swapped_timestamps(ctx: Context, _: Any) -> None:
    def change(values: np.ndarray) -> np.ndarray:
        at = int(_middle(ctx, len(values), 1)[0])
        values[[at, at + 1]] = values[[at + 1, at]]
        return values

    _mutate_timestamps(ctx, change)


@recipe("repeated_timestamp", "temporal", "One timestamp repeats its predecessor")
def repeated_timestamp(ctx: Context, _: Any) -> None:
    def change(values: np.ndarray) -> np.ndarray:
        at = int(_middle(ctx, len(values), 1)[0])
        values[at] = values[at - 1]
        return values

    _mutate_timestamps(ctx, change)


@recipe("timestamp_gap", "temporal", "A gap of N sample intervals, then shifted time", (1.5, 3.0, 20.0))
def timestamp_gap(ctx: Context, intervals: float) -> None:
    def change(values: np.ndarray) -> np.ndarray:
        values[int(_middle(ctx, len(values), 1)[0]) :] += intervals / ctx.fps
        return values

    _mutate_timestamps(ctx, change)


@recipe("timestamp_jitter", "temporal", "Random timing noise in fractions of the sample interval", (0.05, 0.2))
def timestamp_jitter(ctx: Context, fraction: float) -> None:
    def change(values: np.ndarray) -> np.ndarray:
        return values + ctx.rng.normal(0, fraction / ctx.fps, values.shape)

    _mutate_timestamps(ctx, change)


@recipe("clock_scale", "temporal", "Episode clock runs fast by a factor", (1.01, 1.1, 2.0))
def clock_scale(ctx: Context, factor: float) -> None:
    _mutate_timestamps(ctx, lambda values: values[0] + (values - values[0]) * factor)


@recipe("timestamp_offset", "temporal", "Episode time starts 1000 seconds late")
def timestamp_offset(ctx: Context, _: Any) -> None:
    _mutate_timestamps(ctx, lambda values: values + 1000.0)


def _edit_rows(ctx: Context, keep: Callable[[np.ndarray], np.ndarray]) -> None:
    table, rows = ctx.load()
    order = np.arange(table.num_rows)
    ctx.save(
        table.take(
            pa.array(np.concatenate((order[: rows[0]], rows[keep(np.arange(rows.size))], order[rows[-1] + 1 :])))
        )
    )


@recipe("deleted_rows", "temporal", "Rows deleted mid-episode, metadata unchanged", (1, 10))
def deleted_rows(ctx: Context, count: int) -> None:
    _edit_rows(ctx, lambda order: np.delete(order, _middle(ctx, order.size, count)))


@recipe("duplicated_rows", "temporal", "Rows duplicated mid-episode, metadata unchanged", (1, 10))
def duplicated_rows(ctx: Context, count: int) -> None:
    def keep(order: np.ndarray) -> np.ndarray:
        span = _middle(ctx, order.size, count)
        return np.insert(order, span[0], order[span])

    _edit_rows(ctx, keep)


# ---------------------------------------------------------------------------
# Index and metadata defects
# ---------------------------------------------------------------------------


def _mutate_int_column(ctx: Context, column: str, change: Callable[[np.ndarray], np.ndarray]) -> None:
    table, rows = ctx.load()
    values = np.asarray(ctx.stream_values(table, column))
    values[rows] = change(values[rows].copy())
    ctx.save(ctx.store(table, column, values.tolist()))


@recipe("frame_index_reset", "index", "frame_index restarts mid-episode")
def frame_index_reset(ctx: Context, _: Any) -> None:
    def change(values: np.ndarray) -> np.ndarray:
        values[len(values) // 2 :] -= values[len(values) // 2]
        return values

    _mutate_int_column(ctx, "frame_index", change)


@recipe("global_index_shift", "index", "Global index is offset by 7 in one episode")
def global_index_shift(ctx: Context, _: Any) -> None:
    _mutate_int_column(ctx, "index", lambda values: values + 7)


@recipe("episode_label_bleed", "index", "Trailing rows are labeled with the next episode")
def episode_label_bleed(ctx: Context, _: Any) -> None:
    def change(values: np.ndarray) -> np.ndarray:
        values[-5:] += 1
        return values

    _mutate_int_column(ctx, "episode_index", change)


@recipe("unknown_task", "index", "task_index references a task that does not exist")
def unknown_task(ctx: Context, _: Any) -> None:
    _mutate_int_column(ctx, "task_index", lambda values: values + 100_000)


@recipe("wrong_totals", "metadata", "total_frames and total_episodes in info.json are stale")
def wrong_totals(ctx: Context, _: Any) -> None:
    def change(info: dict[str, Any]) -> None:
        info["total_frames"] = int(info.get("total_frames", 0)) + 100
        info["total_episodes"] = int(info.get("total_episodes", 0)) + 1

    ctx.edit_info(change)


@recipe("wrong_length", "metadata", "Episode length in metadata is off by N", (1, 50))
def wrong_length(ctx: Context, delta: int) -> None:
    def change(records: list[dict[str, Any]]) -> None:
        for record in records:
            if int(record["episode_index"]) == ctx.episode.index:
                record["length"] = int(record["length"]) + delta

    ctx.edit_episode_records(change)


@recipe("stale_file_pointer", "metadata", "LeRobot issue 2401: boundary episode metadata names the previous data file")
def stale_file_pointer(ctx: Context, _: Any) -> None:
    table, _rows = ctx.load()
    labels = table["episode_index"].to_numpy()
    if not (ctx.root / "meta" / "episodes").is_dir():
        raise RecipeSkipped("issue 2401 applies to the v3 layout")
    first_row = int(np.flatnonzero(labels == ctx.episode.index)[0])
    if first_row == 0:
        raise RecipeSkipped("boundary episode must not start the file")
    # Reproduce the converter's rollover: the boundary episode and its successors move to a
    # new file, but only the successors' metadata is updated.
    fresh = pa.array(labels >= ctx.episode.index)
    old_file = table.filter(pa.compute.invert(fresh))
    new_file = table.filter(fresh)
    template = ctx.data_path
    next_name = template.with_name("file-900.parquet")
    replace_parquet(next_name, new_file)
    replace_parquet(template, old_file)
    moved = {int(value) for value in np.unique(labels[labels > ctx.episode.index])}
    source_file = template.name
    current_file = int(source_file.removeprefix("file-").removesuffix(".parquet"))

    def change(records: list[dict[str, Any]]) -> None:
        for record in records:
            if int(record["episode_index"]) in moved and int(record["data/file_index"]) == current_file:
                record["data/file_index"] = 900

    ctx.edit_episode_records(change)


@recipe("overlapping_range", "metadata", "dataset_from_index overlaps the previous episode")
def overlapping_range(ctx: Context, _: Any) -> None:
    def change(records: list[dict[str, Any]]) -> None:
        for record in records:
            if int(record["episode_index"]) == ctx.episode.index:
                if "dataset_from_index" not in record:
                    raise RecipeSkipped("layout has no explicit range")
                record["dataset_from_index"] = int(record["dataset_from_index"]) - 5

    ctx.edit_episode_records(change)


@recipe("missing_data_file", "metadata", "A referenced Parquet file is deleted")
def missing_data_file(ctx: Context, _: Any) -> None:
    ctx.targets |= {item.identifier for item in ctx.episodes if item.data_file == ctx.episode.data_file}
    ctx.data_path.unlink()


@recipe("dropped_column", "metadata", "A declared stream is absent from storage")
def dropped_column(ctx: Context, _: Any) -> None:
    table = pq.read_table(ctx.data_path)
    if "observation.state" not in table.schema.names:
        raise RecipeSkipped("dataset has no observation.state")
    ctx.save(table.drop_columns(["observation.state"]))


@recipe("wrong_declared_shape", "metadata", "info.json declares the wrong action shape")
def wrong_declared_shape(ctx: Context, _: Any) -> None:
    def change(info: dict[str, Any]) -> None:
        if "action" not in info["features"]:
            raise RecipeSkipped("dataset has no action")
        info["features"]["action"]["shape"] = [int(info["features"]["action"]["shape"][0]) + 1]

    ctx.edit_info(change)


@recipe("wrong_declared_dtype", "metadata", "info.json declares a different numeric type")
def wrong_declared_dtype(ctx: Context, _: Any) -> None:
    def change(info: dict[str, Any]) -> None:
        if "action" not in info["features"]:
            raise RecipeSkipped("dataset has no action")
        current = str(info["features"]["action"]["dtype"])
        info["features"]["action"]["dtype"] = "float64" if current == "float32" else "float32"

    ctx.edit_info(change)


@recipe("wrong_declared_fps", "metadata", "info.json declares double the true FPS")
def wrong_declared_fps(ctx: Context, _: Any) -> None:
    ctx.edit_info(lambda info: info.__setitem__("fps", float(info["fps"]) * 2))


@recipe("orphan_parquet", "metadata", "A stored Parquet file is not referenced by any episode")
def orphan_parquet(ctx: Context, _: Any) -> None:
    replace_bytes(ctx.data_path.with_name("orphan-copy.parquet"), ctx.data_path.read_bytes())


# ---------------------------------------------------------------------------
# Video defects
# ---------------------------------------------------------------------------


@recipe("video_bitflips", "video", "Random byte corruption inside the video payload", (1, 20, 200), touches_video=True)
def video_bitflips(ctx: Context, flips: int) -> None:
    _stream, path = ctx.video_path()
    payload = bytearray(path.read_bytes())
    for position in ctx.rng.integers(int(len(payload) * 0.1), int(len(payload) * 0.8), flips):
        payload[int(position)] ^= 0xFF
    replace_bytes(path, bytes(payload))


@recipe("video_truncated", "video", "The video file loses a fraction of its tail", (0.05, 0.5), touches_video=True)
def video_truncated(ctx: Context, fraction: float) -> None:
    _stream, path = ctx.video_path()
    payload = path.read_bytes()
    replace_bytes(path, payload[: int(len(payload) * (1 - fraction))])


@recipe("video_missing", "video", "A referenced video file is deleted", touches_video=True)
def video_missing(ctx: Context, _: Any) -> None:
    _stream, path = ctx.video_path()
    path.unlink()


def _frame_edit(ctx: Context, change: Callable[[int, int, np.ndarray], list[np.ndarray]]) -> None:
    def wrapped(index: int, start: int, end: int, frame: np.ndarray) -> list[np.ndarray]:
        return change(index - start, end - start, frame) if start <= index < end else [frame]

    ctx.rewrite_video(wrapped)
    ctx.targets = {ctx.episode.identifier}


@recipe(
    "frozen_camera", "video", "Camera repeats one frame for N frames", (10, 60), touches_video=True, needs_control=True
)
def frozen_camera(ctx: Context, count: int) -> None:
    held: list[np.ndarray] = []
    start = _moving_frame(ctx, ctx.episode.length, count)

    def change(relative: int, length: int, frame: np.ndarray) -> list[np.ndarray]:
        if relative == start:
            held.append(frame)
        return [held[0]] if start <= relative < start + count and held else [frame]

    _frame_edit(ctx, change)


def _moving_frame(ctx: Context, length: int, count: int) -> int:
    """Place a freeze where the robot moves most, since a still camera on a still robot is no defect."""
    table, rows = ctx.load()
    if "observation.state" not in table.schema.names or length <= count + 1:
        return max(0, length // 3)
    state = np.asarray([table["observation.state"][int(row)].as_py() for row in rows], dtype=float)
    state = state.reshape(len(state), -1)
    speed = np.abs(np.diff(state, axis=0)) / (np.ptp(state, axis=0) + 1e-9)
    totals = np.convolve(speed.max(axis=1), np.ones(count), mode="valid")
    return int(np.argmax(totals))


def _paint(ctx: Context, count: int, value: int) -> None:
    def change(relative: int, length: int, frame: np.ndarray) -> list[np.ndarray]:
        return [np.full_like(frame, value)] if length // 3 <= relative < length // 3 + count else [frame]

    _frame_edit(ctx, change)


@recipe("black_frames", "video", "N black frames", (3, 60), touches_video=True, needs_control=True)
def black_frames(ctx: Context, count: int) -> None:
    _paint(ctx, count, 0)


@recipe("saturated_frames", "video", "N fully saturated white frames", (3, 60), touches_video=True, needs_control=True)
def saturated_frames(ctx: Context, count: int) -> None:
    _paint(ctx, count, 255)


@recipe(
    "dropped_frames",
    "video",
    "N frames dropped mid-episode, permanently desynchronizing it",
    (1, 5),
    touches_video=True,
    needs_control=True,
)
def dropped_frames(ctx: Context, count: int) -> None:
    def change(relative: int, length: int, frame: np.ndarray) -> list[np.ndarray]:
        return [] if length // 2 <= relative < length // 2 + count else [frame]

    _frame_edit(ctx, change)


@recipe(
    "half_rate_camera",
    "video",
    "Every second frame repeats, as from a half-rate camera",
    touches_video=True,
    needs_control=True,
)
def half_rate_camera(ctx: Context, _: Any) -> None:
    held: list[np.ndarray] = []

    def change(relative: int, _length: int, frame: np.ndarray) -> list[np.ndarray]:
        if relative % 2 == 0:
            held[:] = [frame]
        return [held[0]] if held else [frame]

    _frame_edit(ctx, change)


@recipe("reversed_episode", "video", "An episode's frames play in reverse", touches_video=True, needs_control=True)
def reversed_episode(ctx: Context, _: Any) -> None:
    buffered: list[np.ndarray] = []

    def change(relative: int, length: int, frame: np.ndarray) -> list[np.ndarray]:
        buffered.append(frame)
        return buffered[::-1] if relative == length - 1 else []

    _frame_edit(ctx, change)


@recipe(
    "video_range_drift",
    "video",
    "LeRobot issue 3177 class: from/to_timestamp drift by N frames",
    (1, 15),
    touches_video=True,
)
def video_range_drift(ctx: Context, frames: int) -> None:
    stream, _path = ctx.video_path()
    ctx.targets = {ctx.episode.identifier}

    def change(records: list[dict[str, Any]]) -> None:
        for record in records:
            if int(record["episode_index"]) == ctx.episode.index:
                prefix = f"videos/{stream}"
                if f"{prefix}/from_timestamp" not in record:
                    raise RecipeSkipped("layout has no explicit video range")
                record[f"{prefix}/from_timestamp"] = float(record[f"{prefix}/from_timestamp"]) + frames / ctx.fps
                record[f"{prefix}/to_timestamp"] = float(record[f"{prefix}/to_timestamp"]) + frames / ctx.fps

    ctx.edit_episode_records(change)


@recipe("swapped_cameras", "video", "Two camera streams are swapped", touches_video=True)
def swapped_cameras(ctx: Context, _: Any) -> None:
    if len(ctx.video_streams) < 2:
        raise RecipeSkipped("dataset has one camera")
    _first, first = ctx.video_path(ctx.video_streams[0])
    _second, second = ctx.video_path(ctx.video_streams[1])
    left, right = first.read_bytes(), second.read_bytes()
    replace_bytes(first, right)
    replace_bytes(second, left)


# ---------------------------------------------------------------------------
# Benign transforms: any new finding here is a ground-truth false alarm
# ---------------------------------------------------------------------------


@recipe("benign_row_groups", "benign", "Parquet rewritten with small row groups", benign=True)
def benign_row_groups(ctx: Context, _: Any) -> None:
    replace_parquet(ctx.data_path, pq.read_table(ctx.data_path), row_group_size=64)


@recipe("benign_compression", "benign", "Parquet rewritten with ZSTD compression", benign=True)
def benign_compression(ctx: Context, _: Any) -> None:
    replace_parquet(ctx.data_path, pq.read_table(ctx.data_path), compression="zstd")


@recipe("benign_column_order", "benign", "Parquet columns stored in reverse order", benign=True)
def benign_column_order(ctx: Context, _: Any) -> None:
    table = pq.read_table(ctx.data_path)
    ctx.save(table.select(table.schema.names[::-1]))


@recipe("benign_reencode", "benign", "Video re-encoded with the same frames", benign=True, touches_video=True)
def benign_reencode(ctx: Context, _: Any) -> None:
    ctx.rewrite_video(lambda _index, _start, _end, frame: [frame])


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


def benchmark_config(extra: dict[str, RuleSettings] | None = None) -> Config:
    """Keep default thresholds; lift only the finding cap, which would hide target episodes."""
    rules = {
        rule.metadata.id: RuleSettings(options={"max_findings": UNCAPPED_FINDINGS})
        for rule in BUILTIN_RULES
        if "max_findings" in rule.metadata.option_defaults
    }
    return Config(cache=CacheSettings(enabled=False), rules={**rules, **(extra or {})})


def finding_keys(report: Report) -> set[tuple[str, str | None, str]]:
    keys: set[tuple[str, str | None, str]] = set()
    for result in report.results:
        if result.status == RuleStatus.ERRORED:
            keys.add((result.rule_id, None, "errored"))
        for item in result.findings:
            level = "blocking" if item.severity in BLOCKING else "advisory"
            keys.add((result.rule_id, item.location.episode, level))
    return keys


def classify(new: set[tuple[str, str | None, str]], targets: set[str]) -> dict[str, Any]:
    """Credit only findings on the injected episodes or dataset-level findings."""
    credited = {key for key in new if key[1] in targets or key[1] is None}
    findings = {key for key in credited if key[2] != "errored"}
    if any(key[1] in targets for key in findings):
        outcome = "localized"
    elif findings:
        outcome = "dataset_level"
    elif credited:
        outcome = "failed_closed"
    else:
        outcome = "missed"
    return {
        "outcome": outcome,
        "detected": outcome != "missed",
        "blocks_ci": any(key[2] in {"blocking", "errored"} for key in credited),
        "rules": sorted({key[0] for key in credited}),
    }


def stable_seed(*parts: Any) -> int:
    return int.from_bytes(hashlib.sha256(repr(parts).encode()).digest()[:8], "big")


class DatasetBench:
    """Hold one source's clean baseline and reuse video statistics for untouched videos."""

    def __init__(self, identifier: str, source: Path, work: Path):
        self.identifier = identifier
        self.source = source
        self.work = work / identifier
        self.view = discover(source)
        self.inventory = self.view.inventory
        self.clean = run_validation(self.view, benchmark_config(), allow_config_plugins=False)
        self.baseline = finding_keys(self.clean)
        self.analysis = dict(getattr(self.view, "_video_analysis_cache", {}))
        self.probes = dict(getattr(self.view, "_video_probes", {}))
        self.oracle = oracle_contract(self.view)
        self.oracle_baseline = finding_keys(self._validate(self.view, self.oracle))
        self.flagged_episodes = {key[1] for key in self.baseline if key[1] is not None}
        self.controls: dict[tuple[str, str | None], set[tuple[str, str | None, str]]] = {}

    def _validate(self, dataset: Any, config: Config) -> Report:
        return run_validation(dataset, config, allow_config_plugins=False)

    def _prepared(self, root: Path) -> Any:
        dataset = discover(root)
        clean = {episode.index: episode for episode in self.inventory.episodes}
        cache = getattr(dataset, "_video_analysis_cache", None)
        if cache is None:
            return dataset
        probes = getattr(dataset, "_video_probes", {})
        for relative, probe in self.probes.items():
            if (root / relative).is_symlink():
                probes[relative] = probe
        for episode in dataset.inventory.episodes:
            reference = clean.get(episode.index)
            for stream, relative in episode.video_files.items():
                key = (episode.index, stream)
                unchanged = (
                    reference is not None
                    and reference.video_files.get(stream) == relative
                    and reference.video_ranges.get(stream) == episode.video_ranges.get(stream)
                    and (root / relative).is_symlink()
                )
                if unchanged and key in self.analysis:
                    cache[key] = self.analysis[key]
        return dataset

    def _target(self, rng: np.random.Generator) -> Episode:
        usable = [
            episode
            for episode in self.inventory.episodes
            if episode.length >= 12 and episode.identifier not in self.flagged_episodes
        ] or [episode for episode in self.inventory.episodes if episode.length >= 12]
        if not usable:
            raise RecipeSkipped("no episode is long enough")
        return usable[int(rng.integers(len(usable)))]

    def trial(self, item: Recipe, level: Any, seed: int) -> dict[str, Any]:
        rng = np.random.default_rng(stable_seed(item.id, level, seed, self.identifier))
        row: dict[str, Any] = {
            "dataset": self.identifier,
            "recipe": item.id,
            "category": item.category,
            "level": level,
            "seed": seed,
            "benign": item.benign,
        }
        root = self.work / f"{item.id}-{level}-{seed}"
        try:
            episode = self._target(rng)
            link_workspace(self.source, root)
            context = Context(
                root=root,
                episodes=self.inventory.episodes,
                episode=episode,
                rng=rng,
                fps=float(self.inventory.fps or 30.0),
                video_streams=[stream.key for stream in self.inventory.streams if stream.kind == "video"],
            )
            item.apply(context, level)
            dataset = self._prepared(root)
            report = self._validate(dataset, benchmark_config())
            new = finding_keys(report) - self.baseline
            if item.needs_control:
                before_control = new
                new = new - self._control(episode, seed)
                row["control_masked"] = bool(classify(before_control, context.targets)["detected"]) and not bool(
                    classify(new, context.targets)["detected"]
                )
            if item.benign:
                row.update(
                    outcome="false_alarm" if new else "clean",
                    detected=False,
                    blocks_ci=any(key[2] in {"blocking", "errored"} for key in new),
                    rules=sorted({key[0] for key in new}),
                )
            else:
                row.update(classify(new, context.targets))
                if item.category in {"numeric", "temporal"}:
                    oracle_report = self._validate(self._prepared(root), self.oracle)
                    oracle_new = finding_keys(oracle_report) - self.oracle_baseline
                    row["oracle_detected"] = classify(oracle_new, context.targets)["detected"]
        except RecipeSkipped as skipped:
            row.update(outcome="skipped", reason=str(skipped))
        finally:
            shutil.rmtree(root, ignore_errors=True)
        return row

    def _control(self, episode: Episode, seed: int) -> set[tuple[str, str | None, str]]:
        """Re-encoding alone can change findings, so subtract what the encoder itself causes."""
        stream = next(iter(episode.video_files), None)
        key = (episode.video_files.get(stream or "", ""), stream)
        if key not in self.controls:
            root = self.work / f"control-{seed}-{hashlib.sha256(str(key).encode()).hexdigest()[:10]}"
            try:
                link_workspace(self.source, root)
                context = Context(
                    root=root,
                    episodes=self.inventory.episodes,
                    episode=episode,
                    rng=np.random.default_rng(0),
                    fps=float(self.inventory.fps or 30.0),
                    video_streams=[item.key for item in self.inventory.streams if item.kind == "video"],
                )
                benign_reencode(context, None)
                self.controls[key] = finding_keys(self._validate(self._prepared(root), benchmark_config()))
            finally:
                shutil.rmtree(root, ignore_errors=True)
        return self.controls[key]


def oracle_contract(dataset: Any) -> Config:
    """Bounds and jump limits fitted to this dataset's clean data: the best case for configured rules."""
    limits: dict[str, dict[str, list[float]]] = {}
    jumps: dict[str, list[float]] = {}
    available = {stream.key: stream for stream in dataset.inventory.streams if stream.kind == "numeric"}
    for stream in FLOAT_STATES:
        if stream not in available:
            continue
        low: np.ndarray | None = None
        high: np.ndarray | None = None
        jump: np.ndarray | None = None
        for episode in dataset.inventory.episodes:
            try:
                if episode.data_file is None or stream not in dataset.parquet_schema(episode):
                    continue
                chunks = [
                    np.asarray(batch.columns[stream], dtype=float) for batch in dataset.iter_batches(episode, (stream,))
                ]
            except Exception:  # noqa: BLE001 - a partly broken source simply gets no oracle
                continue
            if not chunks:
                continue
            values = np.concatenate(chunks).reshape(sum(len(chunk) for chunk in chunks), -1)
            low = values.min(axis=0) if low is None else np.minimum(low, values.min(axis=0))
            high = values.max(axis=0) if high is None else np.maximum(high, values.max(axis=0))
            if len(values) > 1:
                delta = np.abs(np.diff(values, axis=0)).max(axis=0)
                jump = delta if jump is None else np.maximum(jump, delta)
        if low is None or high is None or jump is None:
            continue
        margin = (high - low) * 0.1 + 1e-6
        limits[stream] = {"min": (low - margin).tolist(), "max": (high + margin).tolist()}
        jumps[stream] = (jump * 1.1 + 1e-6).tolist()
    extra: dict[str, RuleSettings] = {}
    if limits:
        extra["numeric.configured_bounds"] = RuleSettings(options={"limits": limits, "max_findings": UNCAPPED_FINDINGS})
        extra["numeric.discontinuity"] = RuleSettings(options={"max_delta": jumps, "max_findings": UNCAPPED_FINDINGS})
    return benchmark_config(extra)


def run_dataset(
    identifier: str, source: Path, work: Path, seeds: int, categories: set[str] | None = None
) -> dict[str, Any]:
    bench = DatasetBench(identifier, source, work)
    trials: list[dict[str, Any]] = []
    for item in RECIPES.values():
        if categories and item.category not in categories:
            continue
        for level in item.levels:
            for seed in range(seeds if not item.benign else 1):
                trials.append(bench.trial(item, level, seed))
    shutil.rmtree(bench.work, ignore_errors=True)
    clean_rules: dict[str, int] = {}
    for result in bench.clean.results:
        if result.findings or result.status == RuleStatus.ERRORED:
            clean_rules[result.rule_id] = len(result.findings)
    return {
        "dataset": identifier,
        "episodes": len(bench.inventory.episodes),
        "frames": bench.inventory.total_frames,
        "clean_status": bench.clean.status,
        "clean_rules": clean_rules,
        "trials": trials,
    }


# ---------------------------------------------------------------------------
# Synthetic LeRobot scenes: clean by construction, so any finding is a false alarm
# ---------------------------------------------------------------------------

SYNTHETIC_SCENES: dict[str, dict[str, Any]] = {
    "synth-arm-large": {"width": 240, "height": 300, "speed": 6, "motion": 0.02},
    "synth-arm-small": {"width": 60, "height": 100, "speed": 6, "motion": 0.02},
    "synth-arm-slow": {"width": 240, "height": 300, "speed": 1, "motion": 0.02},
    "synth-still-jitter": {"width": 0, "height": 0, "speed": 0, "motion": 0.0},
}


def build_synthetic(root: Path, scene: dict[str, Any], episodes: int = 8, length: int = 150) -> Path:
    """Write a healthy v3 dataset with a moving object and truthful, moving robot state."""
    import cv2

    if root.exists():
        shutil.rmtree(root)
    (root / "meta" / "episodes" / "chunk-000").mkdir(parents=True)
    (root / "data" / "chunk-000").mkdir(parents=True)
    video = root / "videos" / "observation.images.cam" / "chunk-000"
    video.mkdir(parents=True)
    fps, width, height, dimensions = 30, 640, 480, 6
    rng = np.random.default_rng(stable_seed("synthetic", json.dumps(scene, sort_keys=True)))
    background = cv2.GaussianBlur(rng.integers(0, 255, (height, width, 3), dtype=np.uint8), (0, 0), 15)
    writer = cv2.VideoWriter(str(video / "file-000.mp4"), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    state: list[list[float]] = []
    for _episode in range(episodes):
        phases = rng.uniform(0, 2 * math.pi, dimensions)
        walk = np.sin(np.arange(length)[:, None] / fps * 2.0 + phases) * scene["motion"] * 50
        if not scene["motion"]:
            # A stationary robot with teleoperation-leader jitter above the motion threshold.
            walk = 1.0 + rng.normal(0, 0.01, (length, dimensions))
        state.extend(walk.tolist())
        for frame_index in range(length):
            frame = background.copy()
            if scene["speed"]:
                x = 20 + (frame_index * scene["speed"]) % (width - scene["width"] - 40)
                y = (height - scene["height"]) // 2
                cv2.rectangle(frame, (x, y), (x + scene["width"], y + scene["height"]), (20, 20, 20), -1)
            writer.write(frame)
    writer.release()
    total = episodes * length
    vector = pa.list_(pa.float32(), dimensions)
    pq.write_table(
        pa.table(
            {
                "timestamp": pa.array(np.tile(np.arange(length) / fps, episodes).tolist(), pa.float64()),
                "frame_index": pa.array(np.tile(np.arange(length), episodes).tolist(), pa.int64()),
                "episode_index": pa.array(np.repeat(np.arange(episodes), length).tolist(), pa.int64()),
                "index": pa.array(list(range(total)), pa.int64()),
                "task_index": pa.array([0] * total, pa.int64()),
                "observation.state": pa.array(state, vector),
                "action": pa.array(state, vector),
            }
        ),
        root / "data" / "chunk-000" / "file-000.parquet",
    )
    camera = "videos/observation.images.cam"
    pq.write_table(
        pa.Table.from_pydict(
            {
                "episode_index": list(range(episodes)),
                "length": [length] * episodes,
                "tasks": [["task"]] * episodes,
                "data/chunk_index": [0] * episodes,
                "data/file_index": [0] * episodes,
                "dataset_from_index": [index * length for index in range(episodes)],
                "dataset_to_index": [(index + 1) * length for index in range(episodes)],
                f"{camera}/chunk_index": [0] * episodes,
                f"{camera}/file_index": [0] * episodes,
                f"{camera}/from_timestamp": [index * length / fps for index in range(episodes)],
                f"{camera}/to_timestamp": [(index + 1) * length / fps for index in range(episodes)],
            }
        ),
        root / "meta" / "episodes" / "chunk-000" / "file-000.parquet",
    )
    pq.write_table(pa.table({"task_index": [0], "task": ["task"]}), root / "meta" / "tasks.parquet")
    declared = {
        name: {"dtype": "int64", "shape": [1]} for name in ("frame_index", "episode_index", "index", "task_index")
    }
    declared["timestamp"] = {"dtype": "float64", "shape": [1]}
    declared["observation.state"] = {"dtype": "float32", "shape": [dimensions]}
    declared["action"] = {"dtype": "float32", "shape": [dimensions]}
    declared["observation.images.cam"] = {"dtype": "video", "shape": [height, width, 3]}
    info = {
        "codebase_version": "v3.0",
        "robot_type": "synthetic",
        "fps": fps,
        "total_episodes": episodes,
        "total_frames": total,
        "features": declared,
        "data_path": "data/chunk-{chunk_index:03d}/file-{file_index:03d}.parquet",
        "video_path": "videos/{video_key}/chunk-{chunk_index:03d}/file-{file_index:03d}.mp4",
    }
    (root / "meta" / "info.json").write_text(json.dumps(info), encoding="utf-8")
    return root


def run_synthetic(identifier: str, work: Path, seeds: int, categories: set[str] | None) -> dict[str, Any]:
    source = build_synthetic(work / "sources" / identifier, SYNTHETIC_SCENES[identifier])
    return run_dataset(identifier, source, work, seeds, categories)


# ---------------------------------------------------------------------------
# MCAP and ROS 2 track
# ---------------------------------------------------------------------------

JOINT_STATE_DEFINITION = """std_msgs/Header header
string[] name
float64[] position
float64[] velocity
float64[] effort
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
"""
MCAP_MESSAGES = 2_000
MCAP_INTERVAL_NS = 10_000_000


def write_recording(path: Path, defect: str | None = None, rng: np.random.Generator | None = None) -> None:
    """Write a 100 Hz JointState recording, optionally with one defect introduced at record time."""
    from mcap_ros2.writer import Writer

    generator = rng or np.random.default_rng(0)
    site = int(generator.integers(MCAP_MESSAGES // 4, 3 * MCAP_MESSAGES // 4))
    with path.open("wb") as output:
        writer = Writer(output)
        schema = writer.register_msgdef("sensor_msgs/msg/JointState", JOINT_STATE_DEFINITION)
        times = [(index + 1) * MCAP_INTERVAL_NS for index in range(MCAP_MESSAGES)]
        publish = list(times)
        if defect == "benign_arrival_reorder":
            times[site], times[site + 1] = times[site + 1], times[site]
            publish = list(times)
        if defect == "log_rollback":
            times = [time - (5_000_000_000 if index >= site else 0) for index, time in enumerate(times)]
            publish = list(times)
        if defect == "duplicate_log_time":
            times[site] = times[site - 1]
        if defect == "cadence_gap":
            times = [time + (2_000_000_000 if index >= site else 0) for index, time in enumerate(times)]
            publish = list(times)
        if defect == "benign_two_publishers":
            publish = [time - (MCAP_INTERVAL_NS * 2 if index % 2 else 0) for index, time in enumerate(times)]
        topic = "/renamed_states" if defect == "missing_topic" else "/joint_states"
        for index, time in enumerate(times):
            if defect == "lost_message" and index == site:
                continue
            position = [float(index), 0.0]
            if defect == "nan_joint" and index == site:
                position[0] = float("nan")
            if defect == "joint_dimension" and index == site:
                position = [0.0]
            writer.write_message(
                topic=topic,
                schema=schema,
                message={
                    "header": {
                        "stamp": {"sec": time // 1_000_000_000, "nanosec": time % 1_000_000_000},
                        "frame_id": "base",
                    },
                    "name": ["a", "b"],
                    "position": position,
                    "velocity": [],
                    "effort": [],
                },
                log_time=time,
                publish_time=publish[index],
                sequence=index + 1,
            )
        writer.finish()


def _chunk_ranges(payload: bytes) -> list[tuple[int, int]]:
    ranges = []
    offset = 8
    while offset < len(payload) - 8:
        opcode = payload[offset]
        length = int.from_bytes(payload[offset + 1 : offset + 9], "little")
        if opcode == 0x06:
            ranges.append((offset + 9, offset + 9 + length))
        offset += 9 + length
    return ranges


MCAP_DEFECTS: dict[str, str] = {
    "log_rollback": "The recorder clock resets 5 seconds backward",
    "duplicate_log_time": "One message repeats its predecessor's log time",
    "cadence_gap": "A 2 second gap on a topic contracted at 100 Hz",
    "lost_message": "One message is lost; the sequence counter skips it",
    "nan_joint": "NaN in one JointState position",
    "joint_dimension": "One JointState has the wrong position length",
    "missing_topic": "A contracted topic is absent",
    "chunk_byte_flip": "One byte flipped inside a CRC-protected chunk",
    "truncated_5pct": "The recording loses 5% of its tail",
    "truncated_50pct": "The recording loses 50% of its tail",
}
MCAP_BENIGN: dict[str, str] = {
    "benign_arrival_reorder": "Two messages stored out of log-time order; the MCAP specification does not forbid this",
    "benign_two_publishers": "Interleaved publisher clocks make publish_time non-monotonic on one topic",
}


def mcap_config() -> Config:
    return benchmark_config(
        {
            "ros2.required_topics": RuleSettings(options={"required_topics": ["/joint_states"]}),
            "ros2.topic_gaps": RuleSettings(
                options={"topic_rates_hz": {"/joint_states": 100}, "max_findings": UNCAPPED_FINDINGS}
            ),
        }
    )


def run_mcap(work: Path, seeds: int) -> dict[str, Any]:
    identifier = "synth-ros2"
    directory = work / identifier
    directory.mkdir(parents=True, exist_ok=True)
    clean_path = directory / "clean.mcap"
    write_recording(clean_path)
    clean = run_validation(discover(clean_path), mcap_config(), allow_config_plugins=False)
    baseline = finding_keys(clean)
    trials: list[dict[str, Any]] = []
    for name, is_benign in [*((key, False) for key in MCAP_DEFECTS), *((key, True) for key in MCAP_BENIGN)]:
        for seed in range(seeds):
            rng = np.random.default_rng(stable_seed(name, seed, identifier))
            path = directory / f"{name}-{seed}.mcap"
            row: dict[str, Any] = {
                "dataset": identifier,
                "recipe": name,
                "category": "benign" if is_benign else "mcap",
                "level": None,
                "seed": seed,
                "benign": is_benign,
            }
            if name in {"chunk_byte_flip", "truncated_5pct", "truncated_50pct"}:
                write_recording(path, None, rng)
                payload = bytearray(path.read_bytes())
                if name == "chunk_byte_flip":
                    start, end = _chunk_ranges(bytes(payload))[0]
                    payload[int(rng.integers(start, end))] ^= 0xFF
                else:
                    payload = payload[: int(len(payload) * (0.95 if name == "truncated_5pct" else 0.5))]
                path.write_bytes(bytes(payload))
            else:
                write_recording(path, name, rng)
            try:
                new = finding_keys(run_validation(discover(path), mcap_config(), allow_config_plugins=False)) - baseline
            except Exception as exc:  # noqa: BLE001 - discovery refusing a recording still fails closed
                new = {(f"discovery:{type(exc).__name__}", None, "errored")}
            if is_benign:
                row.update(
                    outcome="false_alarm" if new else "clean",
                    detected=False,
                    blocks_ci=any(key[2] in {"blocking", "errored"} for key in new),
                    rules=sorted({key[0] for key in new}),
                )
            else:
                row.update(classify(new, set()))
            trials.append(row)
            path.unlink(missing_ok=True)
    shutil.rmtree(directory, ignore_errors=True)
    return {
        "dataset": identifier,
        "episodes": 1,
        "frames": MCAP_MESSAGES,
        "clean_status": clean.status,
        "clean_rules": {
            result.rule_id: len(result.findings)
            for result in clean.results
            if result.findings or result.status == RuleStatus.ERRORED
        },
        "trials": trials,
    }


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def wilson(successes: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return (0.0, 1.0)
    rate = successes / total
    denominator = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - margin), min(1.0, centre + margin))


def rate(rows: Iterable[dict[str, Any]], key: str = "detected") -> dict[str, Any]:
    selected = list(rows)
    hits = sum(bool(row.get(key)) for row in selected)
    low, high = wilson(hits, len(selected))
    return {
        "hits": hits,
        "trials": len(selected),
        "rate": round(hits / len(selected), 4) if selected else None,
        "ci95": [round(low, 4), round(high, 4)],
    }


def macro_rate(rows: list[dict[str, Any]]) -> float | None:
    """Average per recipe, so defects with many levels do not dominate."""
    by_recipe: dict[str, list[bool]] = {}
    for row in rows:
        by_recipe.setdefault(row["recipe"], []).append(bool(row["detected"]))
    if not by_recipe:
        return None
    return round(sum(sum(values) / len(values) for values in by_recipe.values()) / len(by_recipe), 4)


def _no_op(_context: Context, _level: Any) -> None:
    return None


def summarize(results: list[dict[str, Any]], splits: dict[str, str]) -> dict[str, Any]:
    trials = [row for result in results for row in result["trials"] if row["outcome"] != "skipped"]
    skipped = [row for result in results for row in result["trials"] if row["outcome"] == "skipped"]
    defects = [row for row in trials if not row["benign"]]
    benign = [row for row in trials if row["benign"]]
    recipes: list[dict[str, Any]] = []
    catalogue = [
        *RECIPES.values(),
        *(Recipe(name, "mcap", text, _no_op) for name, text in MCAP_DEFECTS.items()),
    ]
    for item in catalogue:
        rows = [row for row in defects if row["recipe"] == item.id]
        if not rows:
            continue
        levels = sorted({row["level"] for row in rows}, key=lambda value: (value is None, value))
        oracle = [row for row in rows if "oracle_detected" in row]
        fired: dict[str, int] = {}
        for row in rows:
            for rule in row["rules"]:
                fired[rule] = fired.get(rule, 0) + 1
        recipes.append(
            {
                "recipe": item.id,
                "category": item.category,
                "description": item.description,
                "detected": rate(rows),
                "blocks_ci": rate(rows, "blocks_ci"),
                "localized": rate([{"detected": row["outcome"] == "localized"} for row in rows]),
                "control_masked": sum(bool(row.get("control_masked")) for row in rows),
                "oracle_detected": rate(oracle, "oracle_detected") if oracle else None,
                "levels": {str(level): rate([row for row in rows if row["level"] == level]) for level in levels},
                "rules": dict(sorted(fired.items(), key=lambda pair: (-pair[1], pair[0]))),
            }
        )
    categories = {
        category: {"macro_detection": macro_rate([row for row in defects if row["category"] == category])}
        for category in sorted({row["category"] for row in defects})
    }
    by_split = {}
    for split in sorted(set(splits.values())):
        rows = [row for row in defects if splits.get(row["dataset"]) == split]
        by_split[split] = {
            "macro_detection": macro_rate(rows),
            "detected": rate(rows),
            "benign_false_alarm": rate(
                [{"detected": row["outcome"] == "false_alarm"} for row in benign if splits.get(row["dataset"]) == split]
            ),
        }
    return {
        "macro_detection": macro_rate(defects),
        "defect_types": len(recipes),
        "trials": len(defects),
        "skipped_trials": len(skipped),
        "by_split": by_split,
        "by_category": categories,
        "recipes": recipes,
        "benign": {
            item.id: {
                "false_alarm": rate(
                    [{"detected": row["outcome"] == "false_alarm"} for row in benign if row["recipe"] == item.id]
                ),
                "rules": sorted({rule for row in benign if row["recipe"] == item.id for rule in row["rules"]}),
            }
            for item in [
                *RECIPES.values(),
                *(Recipe(name, "benign", text, _no_op, benign=True) for name, text in MCAP_BENIGN.items()),
            ]
            if item.benign and any(row["recipe"] == item.id for row in benign)
        },
        "clean_corpus": [
            {
                "dataset": result["dataset"],
                "split": splits.get(result["dataset"]),
                "episodes": result["episodes"],
                "frames": result["frames"],
                "status": result["clean_status"],
                "flagged_rules": result["clean_rules"],
            }
            for result in results
        ],
    }


def render_markdown(summary: dict[str, Any], run_id: str) -> str:
    def percent(value: float | None) -> str:
        return "n/a" if value is None else f"{value * 100:.0f}%"

    lines = [
        f"# Corruption benchmark: {run_id}",
        "",
        "Generated by `python -m validation.benchmark`. Do not edit by hand.",
        "",
        f"Default-contract macro detection: **{percent(summary['macro_detection'])}** across "
        f"{summary['defect_types']} defect types and {summary['trials']} trials "
        f"({summary['skipped_trials']} inapplicable trials skipped).",
        "",
        "| Split | Macro detection | Trials | Benign false alarms |",
        "|---|---:|---:|---:|",
    ]
    for split, values in summary["by_split"].items():
        benign = values["benign_false_alarm"]
        lines.append(
            f"| {split} | {percent(values['macro_detection'])} | {values['detected']['trials']} | "
            f"{benign['hits']}/{benign['trials']} |"
        )
    lines += [
        "",
        "## Detection by defect",
        "",
        "Oracle means bounds and jump limits fitted to the clean dataset, the best case for configured rules.",
        "",
        "| Defect | Category | Detected | 95% CI | Localized | Oracle | Levels | Rules |",
        "|---|---|---:|---|---:|---:|---|---|",
    ]
    for row in sorted(summary["recipes"], key=lambda item: (item["detected"]["rate"], item["recipe"])):
        detected = row["detected"]
        oracle = percent(row["oracle_detected"]["rate"]) if row["oracle_detected"] else "–"
        levels = ", ".join(
            f"{level}: {percent(value['rate'])}" for level, value in row["levels"].items() if level != "None"
        )
        rules = ", ".join(f"`{rule}`" for rule in list(row["rules"])[:3]) or "none"
        low, high = detected["ci95"]
        lines.append(
            f"| `{row['recipe']}` | {row['category']} | "
            f"{percent(detected['rate'])} ({detected['hits']}/{detected['trials']}) | "
            f"{percent(low)}–{percent(high)} | {percent(row['localized']['rate'])} | "
            f"{oracle} | {levels or '–'} | {rules} |"
        )
    lines += ["", "## Benign transforms", "", "| Transform | False alarms | Rules |", "|---|---:|---|"]
    for name, values in summary["benign"].items():
        alarm = values["false_alarm"]
        rules = ", ".join(f"`{rule}`" for rule in values["rules"]) or "none"
        lines.append(f"| `{name}` | {alarm['hits']}/{alarm['trials']} | {rules} |")
    lines += [
        "",
        "## Clean corpus",
        "",
        "A flagged dataset is not automatically a false alarm; see the classification in the benchmark documentation.",
        "",
        "| Dataset | Split | Episodes | Frames | Status | Flagged rules |",
        "|---|---|---:|---:|---|---|",
    ]
    for row in summary["clean_corpus"]:
        flagged = ", ".join(f"`{rule}` ({count})" for rule, count in row["flagged_rules"].items()) or "none"
        lines.append(
            f"| {row['dataset']} | {row['split']} | {row['episodes']} | {row['frames']} | {row['status']} | {flagged} |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(results: list[dict[str, Any]], splits: dict[str, str], output: Path, run_id: str) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    results = sorted(results, key=lambda item: item["dataset"])
    summary = {"schema_version": 1, "run_id": run_id, **summarize(results, splits)}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    (output / "report.md").write_text(render_markdown(summary, run_id), encoding="utf-8")
    fields = [
        "dataset",
        "recipe",
        "category",
        "level",
        "seed",
        "outcome",
        "blocks_ci",
        "oracle_detected",
        "control_masked",
        "rules",
        "reason",
    ]
    with (output / "trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for result in results:
            for row in result["trials"]:
                writer.writerow({**row, "rules": ";".join(row.get("rules", []))})
    return summary


# ---------------------------------------------------------------------------
# Corpus resolution and CLI
# ---------------------------------------------------------------------------


def locate_dataset(record: dict[str, Any], hub_cache: Path, overrides: dict[str, Path]) -> Path | None:
    """Find a pinned snapshot locally; the benchmark itself never downloads anything."""
    subdir = str(record.get("subdir", ""))
    candidates = [
        overrides.get(str(record["id"])),
        hub_cache
        / f"datasets--{str(record['repo_id']).replace('/', '--')}"
        / "snapshots"
        / str(record["revision"])
        / subdir,
        SURVEY_ROOT / str(record["id"]) / subdir,
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "meta" / "info.json").is_file():
            return candidate.resolve()
    return None


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--work", type=Path, default=DEFAULT_WORK)
    result.add_argument("--hub-cache", type=Path, default=Path.home() / ".cache" / "huggingface" / "hub")
    result.add_argument("--seeds", type=int, default=3)
    result.add_argument("--jobs", type=int, default=max(1, (os.cpu_count() or 2) - 2))
    result.add_argument("--split", choices=["dev", "final", "synthetic"], help="Run one corpus split.")
    result.add_argument("--only", action="append", default=[], help="Run one dataset ID; repeatable.")
    result.add_argument("--category", action="append", default=[], help="Run one recipe category; repeatable.")
    result.add_argument("--dataset-root", action="append", default=[], metavar="ID=PATH")
    return result


def run(args: argparse.Namespace) -> None:
    manifest = yaml.safe_load(args.manifest.read_text(encoding="utf-8"))
    overrides = {
        key: Path(value).expanduser().resolve() for key, _, value in (item.partition("=") for item in args.dataset_root)
    }
    records = [
        record
        for record in manifest["datasets"]
        if (not args.only or record["id"] in args.only) and args.split in {None, record["split"]}
    ]
    splits = {str(record["id"]): str(record["split"]) for record in records}
    jobs: dict[str, Path] = {}
    for record in records:
        if record.get("known_defect"):
            print(f"excluded {record['id']}: {record['known_defect']}", flush=True)
            continue
        location = locate_dataset(record, args.hub_cache, overrides)
        if location is None:
            print(f"unavailable {record['id']}: pinned snapshot is not on this machine", flush=True)
            continue
        jobs[str(record["id"])] = location
    categories = set(args.category) or None
    results: list[dict[str, Any]] = []
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        futures = {
            pool.submit(run_dataset, identifier, path, args.work, args.seeds, categories): identifier
            for identifier, path in jobs.items()
        }
        if not args.only and args.split in {None, "synthetic"}:
            for identifier in SYNTHETIC_SCENES:
                splits[identifier] = "synthetic"
                futures[pool.submit(run_synthetic, identifier, args.work, args.seeds, categories)] = identifier
            if not categories or "mcap" in categories:
                splits["synth-ros2"] = "synthetic"
                futures[pool.submit(run_mcap, args.work, args.seeds)] = "synth-ros2"
        for future in as_completed(futures):
            result = future.result()
            results.append(result)
            print(f"finished {futures[future]}: {len(result['trials'])} trials", flush=True)
    summary = write_outputs(results, splits, args.output, str(manifest["run_id"]))
    print(
        json.dumps({key: summary[key] for key in ("macro_detection", "defect_types", "trials", "by_split")}, indent=2)
    )


if __name__ == "__main__":
    run(parser().parse_args())
