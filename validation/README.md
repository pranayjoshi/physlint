# Reproducible release validation

This directory contains the immutable dataset manifest, deterministic corruption recipes, sanitized reports, and publication metrics supporting the Physlint alpha claims. No source dataset or generated corrupted copy is committed.

## Reproduce

Install the development and video dependencies plus the Hugging Face CLI, then run:

```bash
python -m pip install -e '.[video,dev]'
python -m pip install huggingface_hub
python -m validation.harness
```

If the system environment previously had PyArrow 19.0.0, the editable install must be rerun so pip upgrades it to the declared `>=19.0.1` minimum. The harness will otherwise fail before validation while reading nested episode metadata.

The harness downloads exact revisions from `manifest.yaml`, validates all clean sources, creates fully dereferenced working copies of the smallest source, applies one corruption per copy, and verifies the expected rules. Generated source copies live in `validation/.work/` and are ignored by Git.

For an offline rerun using existing snapshots:

```bash
python -m validation.harness \
  --dataset-root panda=/path/to/panda/snapshot \
  --dataset-root rover=/path/to/rover/snapshot \
  --dataset-root so101=/path/to/so101/snapshot \
  --dataset-root sentinel=/path/to/sentinel/snapshot
```

Committed reports replace machine-local paths with `hf://` or `generated://` identifiers. They contain no images or complete samples. Runtime fields are measurements, not golden assertions; statuses, finding ownership, revisions, counts, and checksums are the release evidence.

The human classification and before/after analysis are in [`docs/validation/real-data-2026-08-23.md`](../docs/validation/real-data-2026-08-23.md). Publication-ready metrics are in [`reports/real-data-2026-08-24/summary.csv`](reports/real-data-2026-08-24/summary.csv).

## MCAP and ROS 2 gate

The second harness combines an exact upstream Foxglove conformance fixture, a revision-pinned real RobotisAI robot episode, and deterministic ROS 2 positive and negative recordings:

```bash
python -m validation.mcap_harness
```

For a fully offline run, first obtain the pinned public fixture and pass it explicitly. Its SHA-256 must match the manifest:

```bash
python -m validation.mcap_harness \
  --recording foxglove-ten-messages=/path/to/pinned-ten-messages.mcap \
  --recording robotis-arx5-button=/path/to/pinned-robotis-episode.mcap
```

The immutable inputs and expected outcomes are in [`mcap_manifest.yaml`](mcap_manifest.yaml). Sanitized evidence is committed under [`reports/mcap-ros2-2026-08-26/`](reports/mcap-ros2-2026-08-26/). Controlled ROS 2 MCAP files are generated locally and are not committed.
