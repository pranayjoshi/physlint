from __future__ import annotations

import numpy as np

from physlint.corruptions import (
    drop_samples,
    freeze_frames,
    insert_non_finite,
    offset_timestamps,
    reorder_samples,
    truncate_episode,
    violate_limit,
)


def test_corruptions_return_copies_without_mutating_sources():
    values = np.arange(12, dtype=float).reshape(6, 2)
    original = values.copy()
    assert drop_samples(values, [1, 3]).shape == (4, 2)
    assert reorder_samples(values, 0, 1)[0].tolist() == [2, 3]
    assert np.isnan(insert_non_finite(values, 2, 1)[2, 1])
    assert np.isinf(insert_non_finite(values, 2, 1, infinite=True)[2, 1])
    assert violate_limit(values, 3, 0, 100)[3, 0] == 100
    assert truncate_episode(values, 2).shape == (2, 2)
    np.testing.assert_array_equal(values, original)


def test_temporal_and_video_corruptions():
    timestamps = np.asarray([0.0, 0.1, 0.2])
    np.testing.assert_allclose(offset_timestamps(timestamps, 0.5), [0.5, 0.6, 0.7])
    frames = np.arange(5 * 2 * 2).reshape(5, 2, 2)
    frozen = freeze_frames(frames, 1, 3)
    np.testing.assert_array_equal(frozen[1], frozen[2])
    np.testing.assert_array_equal(frozen[2], frozen[3])
    assert not np.shares_memory(frozen, frames)
