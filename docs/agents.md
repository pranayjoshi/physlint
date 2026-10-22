# Using Physlint from coding agents

Physlint is a deterministic, read-only preflight and regression gate for robot data. Agents should use the CLI's JSON mode and preserve the distinction between a validation finding and an operational failure.

## Safe workflow

Run configuration-declared Python plugins only when a person has explicitly trusted the configuration. The CLI is safe by default: installed entry-point plugins remain available, while plugins named by `physlint.yaml` are recorded in `ignored_config_plugins` and are not imported.

Safe mode controls plugin loading; configuration can still change rule selection and report/cache destinations. For untrusted datasets in CI, supply a reviewed configuration explicitly with `--config PATH`.

```bash
physlint inspect DATASET_OR_RECORDING --format json
physlint check DATASET_OR_RECORDING --format json --safe
```

For a public Hugging Face dataset, include a revision:

```bash
physlint check \
  hf://datasets/owner/dataset@REVISION \
  --format json \
  --safe
```

Use `--offline` when network access is prohibited. The source must already exist in the Hugging Face cache.

## Interpret results correctly

- Exit `0`: validation completed and the configured contract passed.
- Exit `1`: validation completed with a blocking finding, or comparison found a regression. Parse stdout as a report; this is not an execution failure.
- Exit `2`: command or configuration error.
- Exit `3`: source resolution or adapter error.
- Exit `4`: internal or isolated rule error.
- Exit `130`: interrupted.

With `--format json`, successful validation and validation findings are `Report` documents on stdout. Handled runtime errors are `CliError` documents on stderr.

Command-parser errors, such as a missing argument or unknown option, use the standard CLI diagnostic rather than `CliError`. On exit `2`, agents must also handle non-JSON stderr.

Retrieve the exact contracts with:

```bash
physlint schema report
physlint schema error
physlint schema inventory
physlint schema comparison
```

Every rule result is `passed`, `failed`, `not_run`, or `errored`. Never describe `not_run` as a pass. Never describe an overall pass as proof of task success, policy quality, calibration, or robot safety.

## Recommended agent policy

1. Inspect before checking when the format or streams are unfamiliar.
2. Report rule IDs, affected episodes/streams, observed values, impact, and remediation.
3. Suggest contract changes separately from findings.
4. Do not create a baseline, suppress findings, lower severity, or enable config plugins without explicit human approval.
5. Compare before and after reports when a dataset has changed.
6. Keep reports private unless their paths and evidence have been reviewed for disclosure.

## Python API

The stable entry points are `inspect_dataset`, `check_dataset`, `compare_sources`, and `load_report`. Remote-source, offline, cache, and plugin-safety options mirror the CLI. See [Python API](python-api.md).
