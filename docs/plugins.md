# Plugin SDK

Physlint loads extra rules without putting task-specific heuristics into the default contract. A plugin is a class with `metadata: RuleMetadata` and `run(dataset, options, severity) -> list[Finding]`.

## Load from a quality contract

```yaml
config_version: 1
plugins:
  - ./rules/idle_prefix.py:IdlePrefixRule
```

The spec is `module:Class` or `path.py:Class`. Unknown option keys are rejected. Plugin rule IDs must not collide with built-ins.

```bash
physlint rules --config physlint.yaml
physlint explain example.idle_prefix --config physlint.yaml
physlint check /path/to/dataset --config physlint.yaml
```

## Install via entry points

Packaged plugins can register:

```toml
[project.entry-points."physlint.rules"]
idle_prefix = "my_org_rules:IdlePrefixRule"
```

Installed entry points are loaded on every run, then config `plugins:` are appended.

## Contract

- Read-only. Never mutate source data.
- Deterministic. The same dataset, options, and Physlint version must produce the same fingerprints.
- Bounded. Honor `max_findings` and avoid embedding images or full samples.
- Honest. If required capabilities are missing, the engine records `not_run`; do not pass.
- Documented. Include remediation, limitations, and option defaults.

Set `metadata.adapters` to restrict a plugin to `lerobot` or `mcap`. Leave it empty to participate on every adapter that satisfies the required capabilities.

## Example

`examples/plugins/idle_prefix.py` flags long zero-action prefixes. It is a warning, not a built-in, because idle length is a collection policy rather than a universal integrity failure.
