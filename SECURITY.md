# Security policy

Physlint parses untrusted Parquet metadata and optional video. Run it with the least filesystem access needed and do not treat a successful check as proof that a dataset, policy, or robot is safe.

Please report suspected vulnerabilities privately to the maintainers rather than opening a public issue. Include the Physlint version, operating system, a minimal non-sensitive reproducer, and the potential impact. Do not attach private robot data, operator identities, credentials, or proprietary media.

Physlint runs without telemetry, never overwrites source datasets, and does not embed images in reports. Hugging Face sources perform an explicit download unless `--offline` is set.

Configuration-declared plugins are executable Python. The CLI ignores them by default and records them in `ignored_config_plugins`; pass `--allow-config-plugins` only after reviewing and trusting the configuration and plugin code. Installed `physlint.rules` entry points are treated as part of the trusted Python environment.

Security fixes are supported on the latest released minor version during the alpha period.
