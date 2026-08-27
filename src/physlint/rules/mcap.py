"""Deterministic MCAP container and ROS 2 profile rules."""

from __future__ import annotations

from typing import Any

import numpy as np

from physlint.adapters.mcap import McapAdapter
from physlint.models.dataset import DatasetView
from physlint.models.finding import Finding, Location, Severity
from physlint.models.mcap import McapScan
from physlint.models.rule import Rule, RuleMetadata, RuleNotApplicable
from physlint.rules.common import finding


def _scan(dataset: DatasetView) -> McapScan:
    if not isinstance(dataset, McapAdapter):
        raise RuleNotApplicable("rule requires the MCAP adapter")
    return dataset.scan()


class McapReadableRule:
    metadata = RuleMetadata(
        id="mcap.readable",
        version="1.0.0",
        title="MCAP records and CRCs are readable",
        description="Truncated, corrupt, or unsupported records can make a recording partially or wholly unusable.",
        severity=Severity.ERROR,
        scope="recording",
        cost="linear",
        required_capabilities=frozenset({"mcap"}),
        option_defaults={},
        remediation="Recover the original recording, re-finalize it, or convert it into a new validated MCAP.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        scan = _scan(dataset)
        if scan.read_error is None:
            return []
        return [
            finding(
                self.metadata,
                severity,
                "MCAP scan stopped before the recording could be read completely",
                location=Location(source=dataset.root.name),
                observed=scan.read_error,
                expected="all records readable and every available CRC valid",
            )
        ]


class McapSummaryConsistencyRule:
    metadata = RuleMetadata(
        id="mcap.summary_consistency",
        version="1.0.0",
        title="MCAP summary matches observed records",
        description="Stale statistics or broken references can hide missing messages and incomplete finalization.",
        severity=Severity.ERROR,
        scope="recording",
        cost="linear",
        required_capabilities=frozenset({"mcap"}),
        option_defaults={"max_findings": 50},
        remediation="Re-finalize or rewrite the MCAP so its summary and indexes match the data section.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        scan = _scan(dataset)
        if not scan.summary_present:
            raise RuleNotApplicable("recording has no summary section; coverage is reported by mcap.index_coverage")
        mismatches: list[tuple[str, Any, Any]] = []
        _compare(mismatches, "message_count", scan.message_count, scan.expected_message_count)
        _compare(mismatches, "channel_count", len(scan.channels), scan.expected_channel_count)
        _compare(mismatches, "schema_count", len(scan.observed_schema_ids), scan.expected_schema_count)
        _compare(mismatches, "attachment_count", scan.attachment_count, scan.expected_attachment_count)
        _compare(mismatches, "metadata_count", scan.metadata_count, scan.expected_metadata_count)
        for channel_id, expected in scan.expected_channel_counts.items():
            actual = scan.channels.get(channel_id)
            _compare(
                mismatches,
                f"channel[{channel_id}].message_count",
                actual.message_count if actual else 0,
                expected,
            )
        return [
            finding(
                self.metadata,
                severity,
                f"MCAP summary field {name} does not match observed records",
                location=Location(source=dataset.root.name),
                observed=actual,
                expected=expected,
            )
            for name, actual, expected in mismatches[: int(options["max_findings"])]
        ]


class McapIndexCoverageRule:
    metadata = RuleMetadata(
        id="mcap.index_coverage",
        version="1.0.0",
        title="MCAP contains efficient summary and index coverage",
        description="Missing indexes reduce selective-read and historical validation coverage but may be intentional.",
        severity=Severity.NOTICE,
        scope="recording",
        cost="metadata",
        required_capabilities=frozenset({"mcap"}),
        option_defaults={},
        limitations="ROS 2 fastwrite recordings intentionally omit indexes; this rule is informational.",
        remediation="Post-process long-term recordings with `mcap compress` or `ros2 bag convert` to restore indexes.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        scan = _scan(dataset)
        reasons = []
        if not scan.summary_present:
            reasons.append("summary section is absent")
        if scan.message_count and scan.chunk_index_count == 0:
            reasons.append("chunk indexes are absent")
        if not reasons:
            return []
        return [
            finding(
                self.metadata,
                severity,
                "; ".join(reasons),
                location=Location(source=dataset.root.name),
                observed={"summary": scan.summary_present, "chunk_indexes": scan.chunk_index_count},
                expected="summary and indexes for efficient long-term access",
            )
        ]


class McapChannelSchemaRule:
    metadata = RuleMetadata(
        id="mcap.channel_schema",
        version="1.0.0",
        title="MCAP channel and schema references are coherent",
        description="Missing or conflicting schema declarations prevent deterministic message decoding.",
        severity=Severity.ERROR,
        scope="channel",
        cost="metadata",
        required_capabilities=frozenset({"mcap"}),
        option_defaults={"max_findings": 50},
        remediation="Rewrite channel declarations with stable topic, encoding, and schema references.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        scan = _scan(dataset)
        findings: list[Finding] = []
        by_topic: dict[str, set[tuple[str, str | None, str | None]]] = {}
        for channel in scan.channels.values():
            if channel.schema_id and channel.schema_name is None:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"Channel {channel.channel_id} references missing schema {channel.schema_id}",
                        location=Location(stream=channel.topic, source=dataset.root.name),
                        observed={"schema_id": channel.schema_id},
                        expected="referenced schema exists",
                    )
                )
            by_topic.setdefault(channel.topic, set()).add(
                (channel.message_encoding, channel.schema_name, channel.schema_encoding)
            )
        for topic, declarations in by_topic.items():
            if len(declarations) > 1:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"Topic {topic!r} has conflicting channel declarations",
                        location=Location(stream=topic, source=dataset.root.name),
                        observed=[list(item) for item in sorted(declarations, key=str)],
                        expected="one stable encoding and schema per topic",
                    )
                )
        return findings[: int(options["max_findings"])]


class McapTimestampOrderRule:
    metadata = RuleMetadata(
        id="mcap.timestamp_order",
        version="1.0.0",
        title="MCAP channel timestamps do not move backward",
        description="Backward log or publish time breaks replay ordering and synchronization.",
        severity=Severity.ERROR,
        scope="channel",
        cost="linear",
        required_capabilities=frozenset({"mcap"}),
        option_defaults={"max_findings": 50},
        remediation="Fix recorder clock ordering or split the recording at the clock reset.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        for channel in _scan(dataset).channels.values():
            evidence = (
                ("log", channel.log_rollbacks, channel.log_rollback_count),
                ("publish", channel.publish_rollbacks, channel.publish_rollback_count),
            )
            for label, examples, total in evidence:
                for index, timestamp, delta in examples:
                    findings.append(
                        finding(
                            self.metadata,
                            severity,
                            f"{label.title()} time moved backward on {channel.topic} ({total} transition(s) total)",
                            location=Location(
                                stream=channel.topic,
                                sample_index=index,
                                timestamp=float(timestamp) / 1_000_000_000,
                                source=dataset.root.name,
                            ),
                            observed={"delta_ns": delta, "transition_count": total},
                            expected="timestamp delta >= 0",
                        )
                    )
                    if len(findings) >= int(options["max_findings"]):
                        return findings
        return findings


class McapDuplicateTimestampRule:
    metadata = RuleMetadata(
        id="mcap.duplicate_timestamps",
        version="1.0.0",
        title="MCAP duplicate timestamps are visible",
        description="Repeated timestamps can make ordering ambiguous even when the clock never moves backward.",
        severity=Severity.WARNING,
        scope="channel",
        cost="linear",
        required_capabilities=frozenset({"mcap"}),
        option_defaults={"max_findings": 50},
        remediation="Confirm the recorder provides sufficient timestamp resolution and a deterministic sequence field.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        for channel in _scan(dataset).channels.values():
            count = channel.duplicate_log_time_count
            if count:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"{channel.topic} contains {count} duplicate log timestamp(s)",
                        location=Location(stream=channel.topic, source=dataset.root.name),
                        observed={"duplicate_transitions": count},
                        expected="unique log time or an explicit sequence contract",
                    )
                )
        return findings[: int(options["max_findings"])]


class McapSequenceContinuityRule:
    metadata = RuleMetadata(
        id="mcap.sequence_continuity",
        version="1.0.0",
        title="MCAP sequence counters are continuous when present",
        description="Sequence gaps can reveal dropped messages that timestamps alone do not expose.",
        severity=Severity.WARNING,
        scope="channel",
        cost="linear",
        required_capabilities=frozenset({"mcap"}),
        option_defaults={"max_findings": 50},
        limitations="A counter containing only zero is treated as unspecified.",
        remediation="Inspect transport loss and recorder backpressure around the missing sequence range.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings: list[Finding] = []
        for channel in _scan(dataset).channels.values():
            if not channel.sequence_break_count or channel.first_sequence_break is None:
                continue
            index, previous, current = channel.first_sequence_break
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    f"{channel.topic} has {channel.sequence_break_count} non-contiguous sequence transition(s)",
                    location=Location(stream=channel.topic, sample_index=index, source=dataset.root.name),
                    observed={
                        "previous": previous,
                        "current": current,
                        "transition_count": channel.sequence_break_count,
                    },
                    expected="sequence delta == 1",
                )
            )
        return findings[: int(options["max_findings"])]


class Ros2EncodingRule:
    metadata = RuleMetadata(
        id="ros2.encoding",
        version="1.0.0",
        title="ROS 2 channels use decodable CDR schemas",
        description="Unexpected encodings or missing ros2msg schemas prevent portable ROS 2 decoding.",
        severity=Severity.ERROR,
        scope="topic",
        cost="metadata",
        required_capabilities=frozenset({"ros2"}),
        option_defaults={"max_findings": 50},
        remediation="Record with CDR serialization and embed complete ros2msg schema definitions.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        for channel in _scan(dataset).channels.values():
            valid = channel.message_encoding == "cdr" and channel.schema_encoding == "ros2msg"
            if valid:
                continue
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    f"Topic {channel.topic!r} is not a portable ROS 2 CDR channel",
                    location=Location(stream=channel.topic, source=dataset.root.name),
                    observed={
                        "message_encoding": channel.message_encoding,
                        "schema_encoding": channel.schema_encoding,
                        "schema": channel.schema_name,
                    },
                    expected={"message_encoding": "cdr", "schema_encoding": "ros2msg"},
                )
            )
        return findings[: int(options["max_findings"])]


class Ros2DecodeRule:
    metadata = RuleMetadata(
        id="ros2.decode",
        version="1.0.0",
        title="ROS 2 messages decode completely",
        description="Malformed CDR payloads or incomplete message definitions make topic data unusable.",
        severity=Severity.ERROR,
        scope="topic",
        cost="linear",
        required_capabilities=frozenset({"ros2_decode"}),
        option_defaults={"max_findings": 50},
        remediation="Restore the message definition or recover/re-record malformed payloads.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        for channel in _scan(dataset).channels.values():
            if not channel.decode_error_count:
                continue
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    f"{channel.decode_error_count} message decode error(s) on {channel.topic}",
                    location=Location(stream=channel.topic, source=dataset.root.name),
                    observed={"examples": channel.decode_errors[:3]},
                    expected="all CDR payloads decode with the embedded schema",
                )
            )
        return findings[: int(options["max_findings"])]


class Ros2RequiredTopicsRule:
    metadata = RuleMetadata(
        id="ros2.required_topics",
        version="1.0.0",
        title="Required ROS 2 topics are present",
        description="Missing sensor, state, command, or transform topics make a recording incomplete for its contract.",
        severity=Severity.ERROR,
        scope="recording",
        cost="metadata",
        required_capabilities=frozenset({"ros2"}),
        option_defaults={"required_topics": []},
        remediation="Fix the rosbag topic selection or recorder graph and recollect the session.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        required = list(options["required_topics"])
        if not required:
            raise RuleNotApplicable("no required ROS 2 topics configured")
        available = {channel.topic for channel in _scan(dataset).channels.values()}
        return [
            finding(
                self.metadata,
                severity,
                f"Required topic {topic!r} is missing",
                location=Location(stream=topic, source=dataset.root.name),
                observed="absent",
                expected="present",
            )
            for topic in required
            if topic not in available
        ]


class Ros2TopicGapRule:
    metadata = RuleMetadata(
        id="ros2.topic_gaps",
        version="1.0.0",
        title="ROS 2 topic gaps stay within the cadence contract",
        description="Long per-topic gaps indicate message loss, recorder backpressure, or a stalled sensor.",
        severity=Severity.WARNING,
        scope="topic",
        cost="linear",
        required_capabilities=frozenset({"ros2"}),
        option_defaults={"topic_rates_hz": {}, "max_gap_multiplier": 5.0, "min_messages": 3, "max_findings": 50},
        limitations="Without an explicit rate, the median positive interval is used as the local cadence baseline.",
        remediation="Inspect publisher health, QoS, transport loss, and recorder backpressure around the cited gap.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        rates = options["topic_rates_hz"]
        findings = []
        for channel in _scan(dataset).channels.values():
            if channel.message_count < int(options["min_messages"]) or channel.max_log_gap is None:
                continue
            positive = channel.positive_log_intervals_ns
            if not positive:
                continue
            expected_ns = (
                1_000_000_000 / float(rates[channel.topic]) if channel.topic in rates else float(np.median(positive))
            )
            limit_ns = expected_ns * float(options["max_gap_multiplier"])
            index, timestamp, max_gap = channel.max_log_gap
            if max_gap > limit_ns:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        f"{channel.topic} has a gap above {limit_ns / 1e6:.1f} ms",
                        location=Location(
                            stream=channel.topic,
                            sample_index=index,
                            timestamp=float(timestamp) / 1_000_000_000,
                            source=dataset.root.name,
                        ),
                        observed={"max_gap_ms": float(max_gap) / 1e6},
                        expected={"max_gap_ms": limit_ns / 1e6},
                    )
                )
        return findings[: int(options["max_findings"])]


class Ros2HeaderClockSkewRule:
    metadata = RuleMetadata(
        id="ros2.header_clock_skew",
        version="1.0.0",
        title="ROS 2 header time stays close to MCAP log time",
        description="Excessive header/log skew can misalign sensors when both timestamps share a clock domain.",
        severity=Severity.WARNING,
        scope="topic",
        cost="linear",
        required_capabilities=frozenset({"ros2_decode"}),
        option_defaults={"max_header_skew_ms": None, "max_findings": 50},
        limitations="Requires an explicit threshold because ROS header and recorder clocks may use different domains.",
        remediation="Synchronize clock sources or document and transform the timestamp domains before training.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        configured = options["max_header_skew_ms"]
        if configured is None:
            raise RuleNotApplicable("no maximum ROS header/log skew configured")
        limit_ns = float(configured) * 1_000_000
        findings = []
        for channel in _scan(dataset).channels.values():
            if channel.max_header_skew is None:
                continue
            index, skew = channel.max_header_skew
            if skew <= limit_ns:
                continue
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    f"Header/log skew exceeds {configured} ms on {channel.topic}",
                    location=Location(stream=channel.topic, sample_index=index, source=dataset.root.name),
                    observed={"maximum_absolute_skew_ms": skew / 1e6},
                    expected={"max_header_skew_ms": configured},
                )
            )
            if len(findings) >= int(options["max_findings"]):
                return findings
        return findings


class Ros2SemanticConsistencyRule:
    metadata = RuleMetadata(
        id="ros2.semantic_consistency",
        version="1.0.0",
        title="Known ROS 2 message invariants remain consistent",
        description=(
            "Broken JointState dimensions, image payload sizes, or TF frame identifiers corrupt downstream consumers."
        ),
        severity=Severity.ERROR,
        scope="topic",
        cost="linear",
        required_capabilities=frozenset({"ros2_decode"}),
        option_defaults={"max_findings": 50},
        remediation="Fix the publisher or recorder so every message satisfies its ROS message-level invariants.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        findings = []
        for channel in _scan(dataset).channels.values():
            for message in channel.semantic_errors:
                findings.append(
                    finding(
                        self.metadata,
                        severity,
                        message,
                        location=Location(stream=channel.topic, source=dataset.root.name),
                        observed={
                            "inconsistent_message": message,
                            "total_semantic_errors": channel.semantic_error_count,
                        },
                        expected="ROS message invariants satisfied",
                    )
                )
                if len(findings) >= int(options["max_findings"]):
                    return findings
        return findings


class Ros2TfTreeRule:
    metadata = RuleMetadata(
        id="ros2.tf_tree",
        version="1.0.0",
        title="ROS 2 TF children have a stable parent",
        description="Conflicting TF parents make coordinate transforms ambiguous for perception and control.",
        severity=Severity.WARNING,
        scope="recording",
        cost="linear",
        required_capabilities=frozenset({"ros2_decode"}),
        option_defaults={"max_findings": 50},
        limitations="Dynamic re-parenting may be intentional and should be documented or excluded by contract.",
        remediation="Correct frame IDs or split intentional re-parenting into explicit recording phases.",
    )

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]:
        parents: dict[str, set[str]] = {}
        for channel in _scan(dataset).channels.values():
            for parent, child, _is_static in channel.tf_edges:
                if parent and child and parent != child:
                    parents.setdefault(child, set()).add(parent)
        findings = []
        for child, candidates in sorted(parents.items()):
            if len(candidates) <= 1:
                continue
            findings.append(
                finding(
                    self.metadata,
                    severity,
                    f"TF child {child!r} has multiple parents",
                    location=Location(stream="/tf", source=dataset.root.name),
                    observed={"parents": sorted(candidates)},
                    expected="one stable parent per child frame",
                )
            )
        return findings[: int(options["max_findings"])]


def _compare(target: list[tuple[str, Any, Any]], name: str, actual: Any, expected: Any) -> None:
    if expected is not None and actual != expected:
        target.append((name, actual, expected))


MCAP_RULES: list[Rule] = [
    McapReadableRule(),
    McapSummaryConsistencyRule(),
    McapIndexCoverageRule(),
    McapChannelSchemaRule(),
    McapTimestampOrderRule(),
    McapDuplicateTimestampRule(),
    McapSequenceContinuityRule(),
]

ROS2_RULES: list[Rule] = [
    Ros2EncodingRule(),
    Ros2DecodeRule(),
    Ros2RequiredTopicsRule(),
    Ros2TopicGapRule(),
    Ros2HeaderClockSkewRule(),
    Ros2SemanticConsistencyRule(),
    Ros2TfTreeRule(),
]
