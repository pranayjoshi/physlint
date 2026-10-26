---
name: physlint
description: Inspect, validate, and compare local or revision-pinned Hugging Face robot datasets and MCAP recordings with deterministic Physlint reports.
---

# Physlint

Use Physlint when a task asks whether robot-learning data or a recording is structurally and temporally usable, when debugging a training-data failure, or when comparing two dataset versions.

## Procedure

For installation, dependency, or source-layout problems, run `physlint doctor SOURCE --format json` (SOURCE is optional). Doctor returns its diagnostics on stdout even when it exits 2 for a failed diagnostic; it does not run validation rules or configuration plugins.

1. Run `physlint inspect SOURCE --format json` when the format or available streams are unknown.
2. Run `physlint check SOURCE --format json --safe`. For Hugging Face use `hf://datasets/OWNER/NAME@REVISION`; never omit the revision. Add `--offline` when network access is not allowed.
3. Treat exit code `1` as a completed validation with findings and parse stdout. Treat exit codes `2`, `3`, `4`, and `130` as operational errors. Parse a `CliError` document on stderr when present; missing arguments and unknown options produce ordinary CLI text on exit `2`.
4. Summarize failed, errored, and not-run rules separately. Include rule IDs, locations, impact, and remediation.
5. Use `physlint compare BEFORE AFTER --format json --safe` after changes.

Do not enable config plugins, create baselines, suppress findings, or weaken a contract without explicit user approval. A passing report does not certify task success, policy quality, calibration, or robot safety.

Safe mode ignores configuration-declared Python plugins; installed entry-point plugins remain trusted. For untrusted sources in CI, use a reviewed explicit `--config PATH` because dataset configuration can still select rules and report/cache destinations.

Use `physlint schema report` and `physlint schema error` when implementing a parser.

`init --format json` and `baseline --format json` return a `WriteResult` describing the created file. Their handled failures follow the error schema. Use `schema write` and `schema doctor` for those additional contracts. LeRobot v2.0/v2.1 and v3 use the same public CLI.
