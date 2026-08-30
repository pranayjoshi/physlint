"""Exact episode-duplicate detection without loading an entire dataset."""

from __future__ import annotations

import hashlib
from typing import Any

import numpy as np

from physlint.models.dataset import DatasetView, Episode
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata
from physlint.rules.common import finding, numeric_streams


class ExactDuplicateEpisodesRule:
    metadata = RuleMetadata(
        id="duplication.exact_episodes",
        version="1.0.0",
        title="Episodes are not exact duplicates",
        description="Identical observation/action trajectories waste training budget and leak evaluation signal.",
        severity=Severity.ERROR,
        scope="dataset",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"streams": [], "max_findings": 50},
        remediation="Keep one copy of the duplicated demonstration and drop or recollect the rest.",
        limitations="Compares numeric streams only. Near-duplicates and video-only copies are out of scope.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        requested = list(options["streams"]) or numeric_streams(dataset)
        if not requested:
            return []
        seen: dict[str, str] = {}
        findings: list[Finding] = []
        for episode in dataset.inventory.episodes:
            digest = _episode_digest(dataset, episode, requested)
            previous = seen.get(digest)
            if previous is not None:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"Episode {episode.identifier} is an exact numeric duplicate of {previous}",
                        location=Location(episode=episode.identifier),
                        observed={"duplicate_of": previous, "digest": digest[:16]},
                        expected="unique numeric trajectory",
                    )
                )
                if len(findings) >= options["max_findings"]:
                    return findings
            else:
                seen[digest] = episode.identifier
        return findings


def _episode_digest(dataset: DatasetView, episode: Episode, streams: list[str]) -> str:
    digest = hashlib.sha256()
    available = set(dataset.parquet_schema(episode))
    for stream in streams:
        digest.update(stream.encode())
        if stream not in available:
            digest.update(b"missing")
            continue
        for batch in dataset.iter_batches(episode, (stream,)):
            try:
                values = np.ascontiguousarray(np.asarray(batch.columns[stream], dtype=np.float64))
            except (TypeError, ValueError):
                digest.update(b"non-numeric")
                continue
            digest.update(values.tobytes())
    return digest.hexdigest()


DUPLICATION_RULES: list[Rule] = [ExactDuplicateEpisodesRule()]
