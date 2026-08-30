# Changelog

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
