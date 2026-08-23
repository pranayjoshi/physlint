# Contributing

Use Python 3.11 or newer and install `.[video,dev]`. Before opening a change, run:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

Rules must include positive and negative fixtures, a controlled corruption test where applicable, stable evidence and remediation, documented limitations, and a characterized cost. Adapters must remain read-only, metadata-first, lazy over samples, and explicit about capabilities.

Do not add network access, telemetry, source-data mutation, large fixtures, or a new default dependency without an issue describing the measured requirement.
