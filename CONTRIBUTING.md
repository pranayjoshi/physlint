# Contributing

Use Python 3.11 or newer and install `.[video,dev]`. Before opening a change, run:

```bash
ruff check .
ruff format --check .
mypy
pytest
```

Rules must include positive and negative fixtures, a controlled corruption test where applicable, stable evidence and remediation, documented limitations, and a characterized cost. Adapters must remain read-only, metadata-first, lazy over samples, and explicit about capabilities.

New adapter proposals should start with the format-request issue template and include immutable public healthy examples, controlled defects, stream/episode semantics, and the real failure modes the adapter should catch. See `docs/roadmap.md` for the acceptance gate.

The pinned public release gate is intentionally separate from normal CI because it downloads hundreds of MiB. Maintainers can run it locally with `python -m validation.harness` or trigger the manual real-data workflow.

Do not add network access, telemetry, source-data mutation, large fixtures, or a new default dependency without an issue describing the measured requirement.
