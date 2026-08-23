"""LeRobot structure, schema, stream, and episode checks."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from physlint.models.dataset import DatasetView
from physlint.models.finding import Finding, Location, Severity
from physlint.models.rule import Rule, RuleMetadata
from physlint.rules.common import finding


class RequiredFilesRule:
    metadata = RuleMetadata(
        id="manifest.required_files",
        version="1.0.0",
        title="Required files exist",
        description="Missing metadata, Parquet, or referenced video files make validation incomplete.",
        severity=Severity.ERROR,
        scope="dataset",
        cost="metadata",
        required_capabilities=frozenset({"metadata", "episodes"}),
        option_defaults={"max_findings": 50},
        remediation="Restore or regenerate the missing files; ensure the recorder was finalized.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        required = [dataset.root / "meta" / "info.json", dataset.root / "meta" / "episodes"]
        referenced: set[Path] = set(required)
        for episode in dataset.inventory.episodes:
            if episode.data_file:
                referenced.add(dataset.root / episode.data_file)
            referenced.update(dataset.root / path for path in episode.video_files.values())
        findings = []
        for path in sorted(referenced):
            if path.exists():
                continue
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    f"Required source is missing: {path.relative_to(dataset.root)}",
                    location=Location(source=str(path.relative_to(dataset.root))),
                    observed="missing",
                    expected="file or directory exists",
                )
            )
            if len(findings) >= options["max_findings"]:
                break
        return findings


class SchemaMatchesRule:
    metadata = RuleMetadata(
        id="manifest.schema_matches",
        version="1.0.0",
        title="Declared schema matches stored data",
        description="A declared stream that is absent from Parquet cannot be consumed reliably.",
        severity=Severity.ERROR,
        scope="dataset",
        cost="metadata",
        required_capabilities=frozenset({"metadata", "episodes"}),
        option_defaults={"max_findings": 50},
        remediation="Re-export the dataset so info.json and Parquet schemas agree.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        declared = {stream.key for stream in dataset.inventory.streams if stream.kind != "video"}
        findings = []
        seen_files: set[str] = set()
        for episode in dataset.inventory.episodes:
            if episode.data_file in seen_files:
                continue
            seen_files.add(str(episode.data_file))
            schema = dataset.parquet_schema(episode)
            stored = set(schema)
            for missing in sorted(declared - stored):
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"Declared stream {missing!r} is absent from stored Parquet schema",
                        location=Location(stream=missing, source=episode.data_file),
                        observed="absent",
                        expected="declared column exists",
                    )
                )
                if len(findings) >= options["max_findings"]:
                    return findings
            declarations = {
                stream.key: stream
                for stream in dataset.inventory.streams
                if stream.kind == "numeric" and stream.key in stored
            }
            for key, stream in declarations.items():
                stored_type = str(schema[key]).lower()
                if not _dtype_matches(stream.dtype, stored_type):
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"Declared dtype {stream.dtype!r} for {key} does not match {stored_type}",
                            location=Location(stream=key, source=episode.data_file),
                            observed=stored_type,
                            expected=stream.dtype,
                        )
                    )
                    if len(findings) >= options["max_findings"]:
                        return findings
        return findings


class RequiredStreamsRule:
    metadata = RuleMetadata(
        id="manifest.required_streams",
        version="1.0.0",
        title="Required streams are present",
        description="Training inputs or targets are unavailable when required streams are absent.",
        severity=Severity.ERROR,
        scope="dataset",
        cost="linear",
        required_capabilities=frozenset({"metadata"}),
        option_defaults={"required_streams": ["observation.state", "action"]},
        remediation="Recollect or export the dataset with every stream in the quality contract.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        available = {stream.key for stream in dataset.inventory.streams}
        return [
            finding(
                self.metadata,
                severity,
                f"Required stream {stream!r} is missing",
                location=Location(stream=stream),
                observed="absent",
                expected="present",
            )
            for stream in options["required_streams"]
            if stream not in available
        ]


class UniqueEpisodesRule:
    metadata = RuleMetadata(
        id="episode.unique_ids",
        version="1.0.0",
        title="Episode identifiers are unique",
        description="Duplicate identifiers make findings and train/evaluation membership ambiguous.",
        severity=Severity.ERROR,
        scope="dataset",
        cost="metadata",
        required_capabilities=frozenset({"episodes"}),
        option_defaults={},
        remediation="Assign a stable unique identifier to every episode and re-export metadata.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        seen: set[str] = set()
        findings = []
        for episode in dataset.inventory.episodes:
            if episode.identifier in seen:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"Duplicate episode identifier {episode.identifier!r}",
                        location=Location(episode=episode.identifier),
                        observed=episode.identifier,
                        expected="unique identifier",
                    )
                )
            seen.add(episode.identifier)
        return findings


class EpisodeBoundariesRule:
    metadata = RuleMetadata(
        id="episode.valid_boundaries",
        version="1.0.0",
        title="Episode boundaries are valid",
        description="Empty, overlapping, or inconsistent episode ranges indicate incomplete data.",
        severity=Severity.ERROR,
        scope="episode",
        cost="metadata",
        required_capabilities=frozenset({"episodes"}),
        option_defaults={"allow_empty": False},
        remediation="Finalize recording or rebuild episode metadata from the source logs.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        previous_end: int | None = None
        for episode in dataset.inventory.episodes:
            invalid = episode.length < (0 if options["allow_empty"] else 1)
            if episode.from_index is not None and episode.to_index is not None:
                invalid |= episode.to_index <= episode.from_index
                invalid |= episode.to_index - episode.from_index != episode.length
                if previous_end is not None:
                    invalid |= episode.from_index < previous_end
                previous_end = episode.to_index
            if episode.data_file is not None:
                stored_rows = sum(
                    len(batch.columns["episode_index"]) for batch in dataset.iter_batches(episode, ("episode_index",))
                )
                invalid |= stored_rows != episode.length
            if invalid:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"Invalid boundaries for {episode.identifier}",
                        location=Location(episode=episode.identifier, source=episode.data_file),
                        observed={
                            "length": episode.length,
                            "from_index": episode.from_index,
                            "to_index": episode.to_index,
                            "stored_rows": stored_rows if episode.data_file is not None else None,
                        },
                        expected="positive length, ordered non-overlapping range matching length",
                    )
                )
        return findings


class ShapeConsistencyRule:
    metadata = RuleMetadata(
        id="manifest.shape_consistency",
        version="1.0.0",
        title="Stream shapes remain consistent",
        description="Shape or joint-count changes can silently corrupt training batches.",
        severity=Severity.ERROR,
        scope="stream",
        cost="linear",
        required_capabilities=frozenset({"numeric", "episodes"}),
        option_defaults={"max_findings": 50},
        remediation="Split incompatible embodiments or re-export values with the declared shape.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        streams = [stream for stream in dataset.inventory.streams if stream.kind == "numeric"]
        for episode in dataset.inventory.episodes:
            available = set(dataset.parquet_schema(episode))
            for stream in streams:
                if stream.key not in available:
                    continue
                for batch in dataset.iter_batches(episode, (stream.key,)):
                    values = batch.columns[stream.key]
                    actual = tuple(values.shape[1:])
                    declared = () if stream.shape == (1,) and values.ndim == 1 else stream.shape
                    if actual != declared:
                        findings.append(
                            finding(
                                self.metadata,
                                severity,
                                f"{stream.key} has stored shape {actual}, declared {stream.shape}",
                                location=Location(
                                    episode=episode.identifier,
                                    stream=stream.key,
                                    source=episode.data_file,
                                ),
                                observed=list(actual),
                                expected=list(stream.shape),
                            )
                        )
                        break
                if len(findings) >= options["max_findings"]:
                    return findings
        return findings


MANIFEST_RULES: list[Rule] = [
    RequiredFilesRule(),
    SchemaMatchesRule(),
    RequiredStreamsRule(),
    UniqueEpisodesRule(),
    EpisodeBoundariesRule(),
    ShapeConsistencyRule(),
]


def _dtype_matches(declared: str, stored: str) -> bool:
    aliases = {
        "float16": ("halffloat", "float16"),
        "float32": ("float", "float32"),
        "float64": ("double", "float64"),
        "bool": ("bool",),
        "string": ("string",),
    }
    candidates = aliases.get(declared.lower(), (declared.lower(),))
    return any(candidate in stored for candidate in candidates)
