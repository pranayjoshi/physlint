# MVP rule specifications

Every built-in rule has a stable ID, semantic version, default severity, deterministic implementation, bounded finding count, remediation, and serialized evidence. `physlint explain RULE_ID` displays the installed contract.

## `temporal.monotonic`

Fails when the difference between adjacent timestamps within an episode is zero or negative. Evidence includes episode, sample index, timestamp, and observed delta. Repeated timestamps fail because sequence order is ambiguous.

## `temporal.max_gap`

Fails when an adjacent positive timestamp delta exceeds an explicit `max_gap_ms` or, by default, twice the interval implied by declared FPS (`max_gap_multiplier: 2.0`). Adjacent violations are grouped into ranges with counts and maximum duration. Negative deltas are left to `temporal.monotonic`, avoiding duplicate interpretations.

## `video.frozen_frames`

Uses shared spatially sampled video statistics to compare adjacent grayscale frames by mean absolute difference. A run longer than `max_consecutive_frames` (default 5) whose differences remain at or below `mean_absolute_difference` (default 0.5 intensity levels) fails only when aligned robot motion crosses `min_motion_fraction` (default 0.25). The first available `motion_streams` entry is used; action precedes observed state by default to avoid treating sensor quantization in a stationary scene as camera failure.

## `numeric.finite_values`

Fails for any NaN or positive/negative infinity in a numeric stream. Evidence identifies the sample and non-finite component indices without embedding source values.

## `episode.valid_boundaries`

Fails for non-positive episode lengths, reversed ranges, a mismatch between declared length and global index range, or overlapping ordered ranges. This catches incomplete recording finalization and inconsistent episode metadata.

## Remaining default rules

- `manifest.required_files`: every required or metadata-referenced source exists.
- `manifest.schema_matches`: every declared non-video feature exists in stored Parquet schemas.
- `manifest.required_streams`: every quality-contract stream is declared.
- `episode.unique_ids`: canonical episode identifiers are unique.
- `manifest.shape_consistency`: stored sample dimensions match `info.json`.
- `temporal.sampling_interval`: cadence remains within a fraction of declared FPS.
- `temporal.stream_overlap`: required streams have a non-null, non-empty value at every episode sample; NaN/Inf belong to `numeric.finite_values`.
- `temporal.observation_action_delay`: separate stream timestamps stay within the delay limit.
- `numeric.configured_bounds`: values respect configured per-stream minima and maxima.
- `numeric.discontinuity`: adjacent values respect configured maximum absolute deltas.
- `video.decode`: decoded frame count matches episode length within tolerance.
- `video.black_frames`: frame mean and standard deviation are not both near zero; adjacent bad frames are grouped.
