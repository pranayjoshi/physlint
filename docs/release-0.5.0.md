# Physlint 0.5.0

This release adds a corruption benchmark and uses it to close detection gaps. It adds 17 rules, makes non-video validation linear in dataset size, and fixes several silent misses. See the [changelog](https://github.com/pranayjoshi/physlint/blob/master/CHANGELOG.md) for breaking changes.

## Detection

The [corruption benchmark](validation/corruption-benchmark.md) injects 58 defect types into revision-pinned public datasets. On 5 datasets reserved from tuning, macro detection with the shipped defaults is 89%, up from 63% before this release, or 66% counting only findings that fail CI by default. The recipes informed the rules, so this is not a real-world catch rate.

New statistical rules report warnings, not failures. They compare each episode with its own dataset and need no robot-specific configuration. `temporal.signal_alignment` is off by default because it flagged many clean episodes.

## Evidence

The [0.5.0 verification directory](https://github.com/pranayjoshi/physlint/tree/master/validation/reports/release-0.5.0) records fresh runs with this release:

- All four pinned LeRobot v3 sources passed, and all three controlled corruptions were detected.
- All four MCAP/ROS 2 cases matched their expected outcomes. The Foxglove `TenMessages` conformance file now passes the default contract: its one-nanosecond reorder is allowed, and its duplicate timestamps are reported as a warning.
- Both public LeRobot v2 sources passed without findings or errors.

Public examples establish scoped compatibility; they do not certify every dataset using that format.

## Upgrading

- Configurations using `mean_absolute_difference` or `min_motion_fraction` for `video.frozen_frames` are rejected; use `max_cell_difference` and `min_run_displacement`.
- The `video` extra now installs PyAV for bitstream and timeline checks. Without PyAV, those rules report `not_run`.
- The `pranayjoshi/physlint@v1` GitHub Action tag still points to 0.4.0. Pin `@v0.5.0` to use this release.

## Known issues

- On macOS, OpenCV and PyAV each bundle FFmpeg's `libavdevice`, which prints an Objective-C duplicate-class warning. Validation and tests were not affected.
- `video.frozen_frames` still warns on some public datasets where joints move but frames do not change; these cases are unresolved.
