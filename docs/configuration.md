# Quality contracts and CI

```bash
physlint init --path physlint.yaml --format json
physlint check /path/to/data --config physlint.yaml
```

The generated YAML is a starting contract. Configure bounds and discontinuity limits for your robot; Physlint leaves those rules `not_run` without meaningful thresholds. Unknown configuration fields are rejected.

## A small contract

```yaml
config_version: 1
adapter: auto
profile: auto
required_streams: [observation.state, action]
fail_on: error
rules:
  temporal.max_gap:
    options:
      max_gap_multiplier: 2.0
reports:
  json: true
  junit: true
  output_dir: .physlint/reports
cache:
  enabled: true
  directory: .physlint/cache
```

Safe mode ignores Python plugins named by the configuration. Installed plugins remain trusted, and configuration still selects rules and filesystem destinations. Pass an explicit reviewed `--config` when checking an untrusted dataset in CI.

## GitHub Action

```yaml
steps:
  - uses: actions/checkout@v4
  - uses: pranayjoshi/physlint@v1
    with:
      source: path/to/dataset
      config: physlint.yaml
```

The Action uploads JSON, JUnit, SARIF, and HTML reports and preserves the validation exit code. Pin a full commit for immutable workflows. `v1` tracks compatible versions of the Action interface; it is separate from Physlint's Python package version. Reading local repository data requires the checkout step. Hub data requires an explicit revision.

## Reviewed exceptions

```bash
physlint baseline /path/to/data --author ada --reason "reviewed recorder issue" \
  --expires 2026-12-01 --output .physlint/baseline.yaml --format json
physlint check /path/to/data --baseline .physlint/baseline.yaml
```

Suppressions identify exact finding fingerprints and retain the reviewer and reason. A new instance of the same rule still fails. Review exceptions before committing them.
