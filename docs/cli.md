# CLI and diagnostics

## Diagnose an installation

```bash
physlint doctor --format json
physlint doctor /path/to/dataset --config physlint.yaml --format json
```

Doctor checks Python, dependency imports, optional video/Hub support, source metadata when provided, and configuration syntax. It does not execute rules or configuration plugins, decode source videos, or create reports/caches. A Hub source may be downloaded unless `--offline` is given. Optional missing dependencies produce warnings; failed diagnostics return exit 2. The JSON diagnostic document remains on stdout in either case.

Doctor cannot run if a required dependency prevents the CLI itself from importing. In that situation, reinstall Physlint in a clean Python environment and run `python -m pip check`.

## Commands

| Command | Purpose |
| --- | --- |
| `inspect SOURCE --format json` | Metadata and capability inventory |
| `check SOURCE --format json` | Validate and report findings |
| `compare BEFORE AFTER --format json` | Detect finding and coverage regressions |
| `rules --format json` | Installed rule contracts |
| `explain RULE --format json` | One rule's assumptions and remediation |
| `demo --format json` | Synthetic positive and negative demonstration |
| `init --format json` | Create `physlint.yaml` |
| `baseline SOURCE --author NAME --reason TEXT --format json` | Write reviewed exceptions |
| `schema NAME` | JSON Schema for a machine document |

Use `physlint COMMAND --help` for all options. `baseline --output PATH` chooses its file destination; `--format json` chooses its stdout format. Existing output files are preserved unless `--force` is supplied. A baseline cannot be created from an incomplete run containing operational rule/adapter errors.

## Exit codes and envelopes

Validation exit 0 means the contract passed; 1 means it completed with blocking findings. Comparison exit 1 means a regression. Operational errors use 2 for configuration/usage, 3 for source/adapter errors, 4 for internal/rule errors, and 130 for interruption.

In JSON mode, successful writes return a `WriteResult` on stdout, with `operation`, `path`, and (for baseline) `suppressions`. Handled operational failures return a `CliError` on stderr. Command-parser failures still use ordinary CLI text on exit 2. Doctor exit 2 has a diagnostic document on stdout, not a runtime error envelope.

```bash
physlint schema doctor
physlint schema write
physlint schema error
physlint schema report
```

The generated JSON Schemas are also available under the documentation site's `schemas/` path.
