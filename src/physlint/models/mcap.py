"""Small immutable observations produced while scanning an MCAP recording."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class McapChannelObservation:
    """Per-channel metadata and timing evidence without retaining message payloads."""

    channel_id: int
    topic: str
    message_encoding: str
    schema_id: int
    schema_name: str | None = None
    schema_encoding: str | None = None
    message_count: int = 0
    log_rollback_count: int = 0
    log_rollbacks: list[tuple[int, int, int]] = field(default_factory=list)
    publish_rollback_count: int = 0
    publish_rollbacks: list[tuple[int, int, int]] = field(default_factory=list)
    duplicate_log_time_count: int = 0
    sequence_break_count: int = 0
    first_sequence_break: tuple[int, int, int] | None = None
    positive_log_intervals_ns: list[int] = field(default_factory=list)
    max_log_gap: tuple[int, int, int] | None = None
    decode_errors: list[str] = field(default_factory=list)
    decode_error_count: int = 0
    max_header_skew: tuple[int, int] | None = None
    semantic_errors: list[str] = field(default_factory=list)
    semantic_error_count: int = 0
    tf_edges: set[tuple[str, str, bool]] = field(default_factory=set)
    previous_log_time_ns: int | None = None
    previous_publish_time_ns: int | None = None
    previous_sequence: int | None = None


@dataclass
class McapScan:
    """Cached recording scan shared by every MCAP and ROS 2 rule."""

    profile: str
    library: str
    summary_present: bool
    chunk_index_count: int
    attachment_count: int
    metadata_count: int
    observed_schema_ids: set[int] = field(default_factory=set)
    channels: dict[int, McapChannelObservation] = field(default_factory=dict)
    message_count: int = 0
    expected_message_count: int | None = None
    expected_channel_counts: dict[int, int] = field(default_factory=dict)
    expected_schema_count: int | None = None
    expected_channel_count: int | None = None
    expected_attachment_count: int | None = None
    expected_metadata_count: int | None = None
    crc_validated: bool = False
    read_error: str | None = None
