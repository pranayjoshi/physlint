"""Canonical, format-independent dataset concepts."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

import numpy as np
from pydantic import BaseModel, ConfigDict, Field


class Stream(BaseModel):
    """A logical time-aligned feature exposed by an adapter."""

    model_config = ConfigDict(frozen=True)

    key: str
    dtype: str
    shape: tuple[int, ...] = ()
    kind: str = "scalar"
    names: list[str] | dict[str, list[str]] | None = None
    units: str | None = None


class Episode(BaseModel):
    """Episode boundaries and source locations without loaded samples."""

    model_config = ConfigDict(frozen=True)

    index: int
    identifier: str
    length: int
    data_file: str | None = None
    from_index: int | None = None
    to_index: int | None = None
    tasks: list[str] = Field(default_factory=list)
    video_files: dict[str, str] = Field(default_factory=dict)
    video_ranges: dict[str, tuple[float, float]] = Field(default_factory=dict)


class DatasetInventory(BaseModel):
    """Cheap metadata inventory returned by ``physlint inspect``."""

    model_config = ConfigDict(frozen=True)

    name: str
    source_revision: str | None = None
    path: str
    adapter: str
    format_version: str
    profile: str | None = None
    robot_type: str | None = None
    fps: float | None = None
    total_frames: int | None = None
    total_messages: int | None = None
    streams: list[Stream]
    episodes: list[Episode]
    capabilities: frozenset[str]


@dataclass(frozen=True)
class SampleBatch:
    """A bounded batch of samples for one episode."""

    episode: Episode
    columns: dict[str, np.ndarray]


@dataclass(frozen=True)
class VideoFrame:
    """A selectively decoded frame with a privacy-safe source reference."""

    episode: Episode
    stream: str
    frame_index: int
    timestamp: float
    image: np.ndarray = field(repr=False)


@dataclass(frozen=True)
class VideoAnalysis:
    """Privacy-safe frame statistics shared by all video rules."""

    frame_indices: np.ndarray
    timestamps: np.ndarray
    mean_intensities: np.ndarray
    stddevs: np.ndarray
    mean_absolute_differences: np.ndarray

    @property
    def decoded_frames(self) -> int:
        return int(self.frame_indices.size)


class DatasetView(Protocol):
    """Lazy adapter contract consumed by rules."""

    root: Path
    inventory: DatasetInventory

    def iter_batches(
        self,
        episode: Episode,
        columns: tuple[str, ...] | None = None,
        batch_size: int = 65_536,
    ) -> Iterator[SampleBatch]: ...

    def iter_video_frames(self, episode: Episode, stream: str, stride: int = 1) -> Iterator[VideoFrame]: ...

    def video_analysis(self, episode: Episode, stream: str) -> VideoAnalysis: ...

    def parquet_schema(self, episode: Episode) -> dict[str, Any]: ...
