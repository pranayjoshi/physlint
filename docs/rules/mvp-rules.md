# MVP rule specifications

Every built-in rule has a stable ID, semantic version, default severity, deterministic implementation, bounded finding count, remediation, and serialized evidence. `physlint explain RULE_ID` displays the installed contract.

## `temporal.monotonic`

Fails when a timestamp is NaN or infinite, or when the difference between adjacent finite timestamps within an episode is zero or negative. Evidence includes episode, sample index, timestamp, and observed delta. Repeated timestamps fail because sequence order is ambiguous.

## `temporal.max_gap`

Fails when an adjacent positive timestamp delta exceeds an explicit `max_gap_ms` or, by default, twice the interval implied by declared FPS (`max_gap_multiplier: 2.0`). Adjacent violations are grouped into ranges with counts and maximum duration. Negative deltas are left to `temporal.monotonic`, avoiding duplicate interpretations.

## `video.frozen_frames`

Warning since version 2.0.0. A frame counts as repeated when no cell of a small averaged grid changes by more than `max_cell_difference` (default 2 intensity levels). A run longer than `max_consecutive_frames` (default 5) is reported only if every available `motion_streams` entry moved during it, above its own sample noise, by a root-mean-square `min_run_displacement` of its episode range (default 0.05). It cannot tell a frozen camera from a camera that cannot see the motion.

## `numeric.finite_values`

Fails for any NaN or positive/negative infinity in a numeric stream. Evidence identifies the sample and non-finite component indices without embedding source values.

## `episode.valid_boundaries`

Fails for non-positive episode lengths, reversed ranges, a mismatch between declared length and global index range, or overlapping ordered ranges. This catches incomplete recording finalization and inconsistent episode metadata.

## Remaining default rules

- `manifest.required_files`: every required or metadata-referenced source exists.
- `manifest.schema_matches`: every declared non-video feature exists in stored Parquet schemas.
- `manifest.required_streams`: every quality-contract stream is declared.
- `episode.unique_ids`: canonical episode identifiers are unique.
- `episode.index_columns`: `frame_index` counts from zero and `index` follows the declared episode range.
- `episode.task_references`: every stored `task_index` exists in task metadata; `not_run` without readable task metadata.
- `manifest.declared_totals`: `total_frames` and `total_episodes` in `info.json` match episode metadata.
- `manifest.orphan_files`: warns about stored Parquet or MP4 files that no episode references.
- `temporal.episode_start`: an episode's first timestamp matches the dataset median within one sample interval.
- `temporal.clock_drift`: an episode's duration matches its sample count and FPS within one sample interval.
- `video.bitstream`: PyAV decodes each video file without errors; `not_run` without PyAV.
- `video.timeline`: episode video ranges continue each other, hold the expected number of stored frames, and end with the file; `not_run` without PyAV.

## Statistical rules

These compare an episode with its own dataset, so they report anomalies rather than proof. They default to warnings, and most need at least five episodes.

- `numeric.outlier_jumps`: a one-sample step far beyond the dataset's usual largest step.
- `numeric.episode_envelope`: an episode far outside the range of the others.
- `numeric.stuck_channels`: a channel constant for an episode while it varies elsewhere.
- `numeric.noise_level`: sample noise far above the dataset's usual level.
- `numeric.action_state_coupling`: a state joint stops tracking its action.
- `temporal.signal_alignment`: action, state, or video timing differs from the dataset's usual lag, or video matches motion better reversed. This rule is currently noisy; see the [benchmark](../validation/corruption-benchmark.md).
- `duplication.near_episodes`: equal-length action trajectories that are nearly identical.
- `video.repeated_frames`: a camera repeats many frames during motion.
- `video.camera_identity`: a view looks like another camera's stream.
- `manifest.shape_consistency`: stored sample dimensions match `info.json`.
- `temporal.sampling_interval`: cadence remains within a fraction of declared FPS.
- `temporal.stream_overlap`: required streams have a non-null, non-empty value at every episode sample; NaN/Inf belong to `numeric.finite_values`.
- `temporal.observation_action_delay`: separate stream timestamps stay within the delay limit.
- `numeric.configured_bounds`: values respect configured per-stream minima and maxima.
- `numeric.discontinuity`: adjacent values respect configured maximum absolute deltas.
- `video.decode`: decoded frame count matches episode length within tolerance.
- `video.black_frames`: frame mean and standard deviation are not both near zero; adjacent bad frames are grouped.
- `duplication.exact_episodes`: numeric observation/action trajectories are unique across episodes.
