"""Example Physlint plugin: flag long zero-action prefixes.

This rule is intentionally not built-in. Task-specific idle detection belongs in a
quality contract, loaded only when a team opts in.

Load with:

    plugins:
      - examples/plugins/idle_prefix.py:IdlePrefixRule
"""

from __future__ import annotations

from typing import Any

import numpy as np

from physlint.models.dataset import DatasetView
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import RuleMetadata
from physlint.rules.common import finding


class IdlePrefixRule:
    metadata = RuleMetadata(
        id="example.idle_prefix",
        version="1.0.0",
        title="Episode does not begin with a long idle prefix",
        description="Long zero-action prefixes dilute demonstrations and waste training steps.",
        severity=Severity.WARNING,
        scope="episode",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        adapters=frozenset({"lerobot"}),
        option_defaults={
            "motion_stream": "action",
            "max_idle_samples": 8,
            "idle_abs_tolerance": 1e-6,
            "max_findings": 50,
        },
        limitations="Treats near-zero action vectors as idle. Does not infer task success.",
        remediation="Trim leading idle samples during export, or recapture with a shorter pre-motion hold.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        stream = str(options["motion_stream"])
        limit = int(options["max_idle_samples"])
        tolerance = float(options["idle_abs_tolerance"])
        findings: list[Finding] = []
        for episode in dataset.inventory.episodes:
            available = set(dataset.parquet_schema(episode))
            if stream not in available:
                continue
            idle = 0
            for batch in dataset.iter_batches(episode, (stream,)):
                values = np.asarray(batch.columns[stream], dtype=float)
                flat = values.reshape(len(values), -1)
                for row in flat:
                    if np.all(np.abs(row) <= tolerance):
                        idle += 1
                    else:
                        break
                else:
                    continue
                break
            if idle >= limit:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"Episode begins with {idle} idle action samples",
                        location=Location(episode=episode.identifier, stream=stream, sample_index=0),
                        observed={"idle_samples": idle},
                        expected={"max_idle_samples": limit},
                    )
                )
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings
