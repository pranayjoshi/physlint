# Changelog

## Unreleased

### Breaking

- `video.frozen_frames` 2.0.0 is now a warning. `max_cell_difference` replaces `mean_absolute_difference`, and `min_run_displacement` replaces `min_motion_fraction`, so configurations using the old options are rejected.
- `mcap.timestamp_order` 2.0.0 ignores backward steps of up to `max_reorder_ms` and ignores publish time unless `check_publish_time` is set.
- The `video` and `all` extras now install PyAV.

### Added

- Rules: `episode.index_columns`, `episode.task_references`, `manifest.declared_totals`, `manifest.orphan_files`, `temporal.episode_start`, `temporal.clock_drift`, `video.bitstream`, `video.timeline`, `video.repeated_frames`, and `video.camera_identity`.
- Warnings calibrated from the dataset: `numeric.outlier_jumps`, `numeric.episode_envelope`, `numeric.stuck_channels`, `numeric.noise_level`, `numeric.action_state_coupling`, and `duplication.near_episodes`.
- `temporal.signal_alignment`, off by default; enable it in `physlint.yaml`. Rules can now be opt-in.
- `findings_capped` on each rule result, also shown in terminal output.
- A reproducible corruption benchmark with per-defect detection and false-alarm results.

### Fixed

- Detect non-finite timestamps in `temporal.monotonic`, non-finite `JointState` and TF values in `ros2.semantic_consistency`, and saturated frames in `video.black_frames`.
- Fix masked NaNs after a null row, the first-batch sample index in `temporal.sampling_interval`, and the MCAP interval reservoir.
- Report NaN and infinity evidence as text instead of failing the rule that found them.
- Explain unreadable null rows in fixed-size list columns.
- Decode shared Parquet columns once, making non-video validation linear in dataset size.

## 0.4.0 — 2026-10-26

- Read native LeRobot v2.0/v2.1 per-episode Parquet/MP4 and JSONL metadata, with public and controlled compatibility evidence.
- Add `physlint doctor` for runtime, dependency, configuration, and source-layout diagnostics.
- Return versioned JSON write envelopes and operational errors for `init` and `baseline`.
- Publish searchable documentation with automatically deployed GitHub Pages builds.
- Add fresh 0.4.0 release evidence while preserving historical manifests and reports.

- Accept revision-qualified Hugging Face dataset sources through `hf://datasets/owner/name@revision`, with explicit offline and cache controls.
- Ignore executable plugins declared by dataset configuration by default; trusted callers can opt in explicitly.
- Add a zero-setup `physlint demo` command with one healthy and one deterministically corrupted dataset.
- Publish CLI JSON Schemas, structured JSON operational errors, and JSON output for rule explanations.
- Add an agent operating guide, reusable agent skill, Python API guide, and `llms.txt` index.
- Add a reusable GitHub Action that preserves reports even when validation blocks CI.
- Add general bug and feature issue forms.
- Add an 18-second animated launch clip in widescreen and 4:5 social formats, generated from freshly executed demo evidence.
- Verify the final Hub snapshot commit rather than an ancestor cache directory when recording source provenance.

## 0.3.2 — 2026-09-06

- Launch the Physlint Community Evidence Atlas with 23 published observations, community survey context, real defect stories, and stable evidence links.
- Add a public evidence-submission workflow for dataset and recording maintainers.
- Replace the public regressions section with a clearer community narrative while retaining the generated comparison catalog for reproducibility.
- Refresh the PyPI monthly download snapshot to 289 downloads.

## 0.3.1 — 2026-08-30

- Add a stratified LeRobot compatibility survey, kept separate from the four-snapshot release gate.
- Accept Hub feature `names` stored as a single string instead of crashing discovery.

## 0.3.0 — 2026-08-30

- Add `physlint compare` for dataset and report regression diffs, including coverage drift without a quality score.
- Add reviewed baselines via `physlint baseline` and `--baseline`; suppressions require fingerprint, rule ID, author, reason, and optional expiry.
- Add JUnit, SARIF, and local HTML reporters alongside versioned JSON.
- Add a plugin loader for `module:Class` specs and `physlint.rules` entry points, plus an example idle-prefix rule.
- Cache expensive video rule results on disk, keyed by source fingerprint and rule options.
- Detect exact duplicate numeric episodes with `duplication.exact_episodes`.
- Publish Observatory regression evidence generated from committed clean-versus-corruption reports.

## 0.2.0a2

- Refined the Physlint Observatory launch experience and branding.
- Continued validation coverage for LeRobot, MCAP, and ROS 2 workflows.

## 0.2.0a1 — development

- Add standalone generic MCAP discovery, content fingerprints, CRC-aware scanning, and seven container rules.
- Add a ROS 2-over-MCAP profile with portable CDR decode and seven topic/semantic rules.
- Keep timing evidence bounded with exact discontinuity counters and deterministic interval sampling.
- Detect rosbag2 SQLite sources and return explicit MCAP conversion guidance.
- Add pinned Foxglove MCAP evidence, clean/corrupt ROS 2 recipes, and sanitized reports.
- Add the profile-aware Physlint Observatory site for LeRobot, MCAP, and ROS 2 evidence.

## 0.1.0a1 — public alpha

- Add 17 deterministic LeRobot v3 integrity rules and stable CI exit codes.
- Make maximum-gap defaults scale with declared FPS while preserving absolute overrides.
- Require aligned robot motion for frozen-camera findings.
- Share one privacy-safe video analysis pass across video rules.
- Group repeated gap and black-frame evidence.
- Preserve Hugging Face repository identity and pinned source revision.
- Separate NaN/Inf findings from null/empty stream-overlap semantics.
- Add a reproducible four-dataset and three-corruption release gate.

This alpha supports local LeRobot v3.x directories. MCAP/ROS 2 and Robomimic are roadmap items, not implemented adapters.
