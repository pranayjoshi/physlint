"""Pure corruption helpers for testing validators without modifying source datasets."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np


def drop_samples(values: np.ndarray, indices: Sequence[int]) -> np.ndarray:
    """Return a copy with selected rows removed."""
    return np.delete(np.asarray(values), sorted(set(indices)), axis=0)


def reorder_samples(values: np.ndarray, first: int, second: int) -> np.ndarray:
    """Return a copy with two rows swapped."""
    result = np.array(values, copy=True)
    result[[first, second]] = result[[second, first]]
    return result


def offset_timestamps(timestamps: np.ndarray, offset_seconds: float) -> np.ndarray:
    """Return timestamps shifted by an exact constant."""
    return np.asarray(timestamps, dtype=float).copy() + offset_seconds


def freeze_frames(frames: np.ndarray, start: int, length: int) -> np.ndarray:
    """Replace a range with copies of its first frame."""
    result = np.array(frames, copy=True)
    if length > 0:
        result[start : start + length] = result[start]
    return result


def insert_non_finite(values: np.ndarray, sample: int, dimension: int, *, infinite: bool = False) -> np.ndarray:
    """Insert one NaN or infinity into a numeric stream copy."""
    result = np.asarray(values, dtype=float).copy()
    result[sample, dimension] = np.inf if infinite else np.nan
    return result


def violate_limit(values: np.ndarray, sample: int, dimension: int, value: float) -> np.ndarray:
    """Set one numeric component outside a test contract."""
    result = np.asarray(values, dtype=float).copy()
    result[sample, dimension] = value
    return result


def truncate_episode(values: np.ndarray, retained_samples: int) -> np.ndarray:
    """Return only the requested episode prefix."""
    return np.asarray(values)[:retained_samples].copy()
