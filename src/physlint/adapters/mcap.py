"""Read-only MCAP adapter with optional ROS 2 semantic observations."""

from __future__ import annotations

import struct
from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import Any

from mcap.exceptions import McapError
from mcap.reader import make_reader
from mcap.records import Channel, DataEnd, Schema
from mcap.stream_reader import StreamReader
from mcap_ros2.decoder import DecoderFactory

from physlint.adapters.base import AdapterError
from physlint.models.dataset import (
    DatasetInventory,
    Episode,
    SampleBatch,
    Stream,
    VideoAnalysis,
    VideoFrame,
)
from physlint.models.mcap import McapChannelObservation, McapScan

MCAP_MAGIC = b"\x89MCAP0\r\n"
MAX_EVIDENCE_EXAMPLES = 50
INTERVAL_RESERVOIR_SIZE = 4_096


class McapAdapter:
    """Expose MCAP recording metadata and one cached integrity scan."""

    name = "mcap"
    version = "1.0"

    def __init__(self, path: Path, profile: str = "auto"):
        self.root = path
        self._requested_profile = profile
        self._scan_cache: McapScan | None = None
        header_profile, library, summary = self._read_metadata()
        resolved_profile = self._resolve_profile(header_profile)
        streams: list[Stream] = []
        message_count: int | None = None
        if summary is not None:
            for channel in sorted(summary.channels.values(), key=lambda item: (item.topic, item.id)):
                streams.append(_stream_from_channel(channel, summary.schemas.get(channel.schema_id)))
            if summary.statistics is not None:
                message_count = int(summary.statistics.message_count)
        if summary is None:
            scan = self.scan()
            streams = [
                Stream(
                    key=channel.topic,
                    dtype=channel.schema_name or channel.message_encoding or "bytes",
                    kind=_stream_kind(channel.schema_name),
                )
                for channel in sorted(scan.channels.values(), key=lambda item: (item.topic, item.channel_id))
            ]
            message_count = scan.message_count
        capabilities = {"mcap", "channels", "message_timestamps"}
        if resolved_profile == "ros2":
            capabilities.update({"ros2", "ros2_decode"})
        episode = Episode(
            index=0,
            identifier=path.stem,
            length=message_count or 0,
            tasks=[],
        )
        self.inventory = DatasetInventory(
            name=path.name,
            path=str(path),
            adapter=self.name,
            format_version=self.version,
            profile=resolved_profile,
            total_messages=message_count or 0,
            streams=streams,
            episodes=[episode],
            capabilities=frozenset(capabilities),
        )
        self.header_profile = header_profile
        self.library = library

    def _read_metadata(self) -> tuple[str, str, Any | None]:
        try:
            with self.root.open("rb") as handle:
                reader = make_reader(handle)
                header = reader.get_header()
                return header.profile, header.library, reader.get_summary()
        except (OSError, McapError, ValueError, struct.error) as exc:
            if not has_mcap_magic(self.root):
                raise AdapterError(f"invalid MCAP recording {self.root}: {exc}") from exc
            return "", "unknown", None

    def _resolve_profile(self, header_profile: str) -> str:
        if self._requested_profile == "ros2":
            return "ros2"
        if self._requested_profile == "generic":
            return "generic"
        return "ros2" if header_profile.lower() == "ros2" else "generic"

    def scan(self) -> McapScan:
        """Read the recording once, validate CRCs, and cache privacy-safe observations."""
        if self._scan_cache is not None:
            return self._scan_cache
        profile = getattr(getattr(self, "inventory", None), "profile", None) or self._resolve_profile("")
        scan = McapScan(
            profile=profile,
            library=getattr(self, "library", "unknown"),
            summary_present=False,
            chunk_index_count=0,
            attachment_count=0,
            metadata_count=0,
        )
        try:
            with self.root.open("rb") as handle:
                reader = make_reader(handle, validate_crcs=True)
                header = reader.get_header()
                scan.profile = self._resolve_profile(header.profile)
                scan.library = header.library
                summary = reader.get_summary()
                if summary is not None:
                    scan.summary_present = True
                    scan.chunk_index_count = len(summary.chunk_indexes)
                    scan.attachment_count = len(summary.attachment_indexes)
                    scan.metadata_count = len(summary.metadata_indexes)
                    for schema_id in summary.schemas:
                        scan.observed_schema_ids.add(schema_id)
                    for channel in summary.channels.values():
                        scan.channels[channel.id] = _channel_observation(
                            channel, summary.schemas.get(channel.schema_id)
                        )
                    if summary.statistics is not None:
                        stats = summary.statistics
                        scan.expected_message_count = int(stats.message_count)
                        scan.expected_channel_counts = {
                            int(channel_id): int(count) for channel_id, count in stats.channel_message_counts.items()
                        }
                        scan.expected_schema_count = int(stats.schema_count)
                        scan.expected_channel_count = int(stats.channel_count)
                        scan.expected_attachment_count = int(stats.attachment_count)
                        scan.expected_metadata_count = int(stats.metadata_count)
                decoder_factory = DecoderFactory() if scan.profile == "ros2" else None
                decoder_cache: dict[int, Any] = {}
                for schema, channel, message in reader.iter_messages(log_time_order=False):
                    observation = scan.channels.setdefault(channel.id, _channel_observation(channel, schema))
                    if schema is not None:
                        scan.observed_schema_ids.add(schema.id)
                        observation.schema_name = schema.name
                        observation.schema_encoding = schema.encoding
                    _observe_timing(
                        observation,
                        int(message.log_time),
                        int(message.publish_time),
                        int(message.sequence),
                    )
                    observation.message_count += 1
                    scan.message_count += 1
                    if decoder_factory is not None:
                        _observe_ros2_message(
                            observation,
                            schema,
                            channel,
                            message.data,
                            int(message.log_time),
                            decoder_factory,
                            decoder_cache,
                        )
                scan.attachment_count = sum(1 for _ in reader.iter_attachments())
                scan.metadata_count = sum(1 for _ in reader.iter_metadata())
                (
                    scan.data_channel_record_count,
                    scan.data_schema_record_count,
                ) = _data_section_declaration_counts(self.root)
                scan.crc_validated = True
        except (OSError, McapError, ValueError, struct.error) as exc:
            scan.read_error = f"{type(exc).__name__}: {exc}"
        self._scan_cache = scan
        return scan

    # MCAP rules consume ``scan`` directly. These methods preserve the format-neutral
    # adapter protocol while making accidental Parquet/video use explicit.
    def parquet_schema(self, episode: Episode) -> dict[str, Any]:
        return {}

    def iter_batches(
        self,
        episode: Episode,
        columns: tuple[str, ...] | None = None,
        batch_size: int = 65_536,
    ) -> Iterator[SampleBatch]:
        raise AdapterError("sample batches require a training-semantic MCAP profile")
        yield  # pragma: no cover

    def iter_video_frames(self, episode: Episode, stream: str, stride: int = 1) -> Iterator[VideoFrame]:
        raise AdapterError("MCAP image messages are validated by the ROS 2 profile")
        yield  # pragma: no cover

    def video_analysis(self, episode: Episode, stream: str) -> VideoAnalysis:
        raise AdapterError("MCAP image messages are validated by the ROS 2 profile")


def has_mcap_magic(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(MCAP_MAGIC)) == MCAP_MAGIC
    except OSError:
        return False


def _data_section_declaration_counts(path: Path) -> tuple[int, int]:
    """Count declarations in the data section, excluding summary copies.

    Summary maps may legitimately retain channels and schemas for topics that
    recorded zero messages. MCAP Statistics counts the declarations written to
    the data section, so comparing it with the summary maps creates false
    corruption findings for those topics.
    """
    channel_count = 0
    schema_count = 0
    with path.open("rb") as handle:
        for record in StreamReader(handle).records:
            if isinstance(record, DataEnd):
                break
            if isinstance(record, Channel):
                channel_count += 1
            elif isinstance(record, Schema):
                schema_count += 1
    return channel_count, schema_count


def _stream_from_channel(channel: Channel, schema: Schema | None) -> Stream:
    return Stream(
        key=channel.topic,
        dtype=schema.name if schema is not None else channel.message_encoding or "bytes",
        kind=_stream_kind(schema.name if schema is not None else None),
    )


def _stream_kind(schema_name: str | None) -> str:
    if schema_name and schema_name.endswith(("/Image", "/CompressedImage")):
        return "image"
    return "message"


def _channel_observation(channel: Channel, schema: Schema | None) -> McapChannelObservation:
    return McapChannelObservation(
        channel_id=channel.id,
        topic=channel.topic,
        message_encoding=channel.message_encoding,
        schema_id=channel.schema_id,
        schema_name=schema.name if schema is not None else None,
        schema_encoding=schema.encoding if schema is not None else None,
    )


def _observe_timing(
    observation: McapChannelObservation,
    log_time: int,
    publish_time: int,
    sequence: int,
) -> None:
    index = observation.message_count
    previous_log = observation.previous_log_time_ns
    if previous_log is not None:
        delta = log_time - previous_log
        if delta < 0:
            observation.log_rollback_count += 1
            if len(observation.log_rollbacks) < MAX_EVIDENCE_EXAMPLES:
                observation.log_rollbacks.append((index, log_time, delta))
        elif delta == 0:
            observation.duplicate_log_time_count += 1
        else:
            _sample_interval(observation, delta, index)
            if observation.max_log_gap is None or delta > observation.max_log_gap[2]:
                observation.max_log_gap = (index, log_time, delta)
    previous_publish = observation.previous_publish_time_ns
    if previous_publish is not None and publish_time < previous_publish:
        delta = publish_time - previous_publish
        observation.publish_rollback_count += 1
        if len(observation.publish_rollbacks) < MAX_EVIDENCE_EXAMPLES:
            observation.publish_rollbacks.append((index, publish_time, delta))
    previous_sequence = observation.previous_sequence
    if previous_sequence is not None and (previous_sequence or sequence) and sequence - previous_sequence != 1:
        observation.sequence_break_count += 1
        if observation.first_sequence_break is None:
            observation.first_sequence_break = (index, previous_sequence, sequence)
    observation.previous_log_time_ns = log_time
    observation.previous_publish_time_ns = publish_time
    observation.previous_sequence = sequence


def _sample_interval(observation: McapChannelObservation, delta: int, index: int) -> None:
    sample = observation.positive_log_intervals_ns
    if len(sample) < INTERVAL_RESERVOIR_SIZE:
        sample.append(delta)
        return
    slot = (index * 2_654_435_761) % index
    if slot < INTERVAL_RESERVOIR_SIZE:
        sample[slot] = delta


def _observe_ros2_message(
    observation: McapChannelObservation,
    schema: Schema | None,
    channel: Channel,
    payload: bytes,
    log_time: int,
    factory: DecoderFactory,
    cache: dict[int, Any],
) -> None:
    try:
        decoder = cache.get(channel.id)
        if decoder is None:
            decoder = factory.decoder_for(channel.message_encoding, schema)
            if decoder is None:
                raise ValueError(
                    f"unsupported ROS 2 encoding {channel.message_encoding!r} with schema "
                    f"{getattr(schema, 'encoding', None)!r}"
                )
            cache[channel.id] = decoder
        decoded = decoder(payload)
        header_stamp = _header_stamp_ns(decoded)
        if header_stamp is not None:
            skew = abs(header_stamp - log_time)
            index = observation.message_count - 1
            if observation.max_header_skew is None or skew > observation.max_header_skew[1]:
                observation.max_header_skew = (index, skew)
        _observe_ros2_semantics(observation, decoded)
    except Exception as exc:  # noqa: BLE001 - malformed messages are validation evidence
        observation.decode_error_count += 1
        if len(observation.decode_errors) < MAX_EVIDENCE_EXAMPLES:
            observation.decode_errors.append(f"{type(exc).__name__}: {exc}")


def _observe_ros2_semantics(observation: McapChannelObservation, message: Any) -> None:
    schema_name = observation.schema_name or ""
    if schema_name.endswith("/JointState"):
        names = list(_field(message, "name", []))
        for field_name in ("position", "velocity", "effort"):
            values = list(_field(message, field_name, []))
            if values and len(values) != len(names):
                _add_semantic_error(
                    observation, f"{field_name} has {len(values)} values but name has {len(names)} entries"
                )
    elif schema_name.endswith("/TFMessage"):
        is_static = observation.topic == "/tf_static"
        for transform in _field(message, "transforms", []):
            header = _field(transform, "header", None)
            parent = str(_field(header, "frame_id", ""))
            child = str(_field(transform, "child_frame_id", ""))
            if not parent or not child:
                _add_semantic_error(observation, "TF transform has an empty parent or child frame")
            elif parent == child:
                _add_semantic_error(observation, f"TF transform self-references frame {parent!r}")
            observation.tf_edges.add((parent, child, is_static))
    elif schema_name.endswith("/Image"):
        height = int(_field(message, "height", 0))
        step = int(_field(message, "step", 0))
        data = _field(message, "data", b"")
        if height <= 0 or step <= 0 or len(data) != height * step:
            _add_semantic_error(
                observation, f"Image payload has {len(data)} bytes; expected height*step={height * step}"
            )
    elif schema_name.endswith("/CompressedImage"):
        data = _field(message, "data", b"")
        if not data:
            _add_semantic_error(observation, "CompressedImage payload is empty")
        else:
            _validate_compressed_image(observation, bytes(data))


def _add_semantic_error(observation: McapChannelObservation, message: str) -> None:
    observation.semantic_error_count += 1
    if len(observation.semantic_errors) < MAX_EVIDENCE_EXAMPLES:
        observation.semantic_errors.append(message)


def _validate_compressed_image(observation: McapChannelObservation, data: bytes) -> None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return
    encoded = np.frombuffer(data, dtype=np.uint8)
    if cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED) is None:
        _add_semantic_error(observation, "CompressedImage payload cannot be decoded")


def _header_stamp_ns(message: Any) -> int | None:
    header = _field(message, "header", None)
    stamp = _field(header, "stamp", None)
    if stamp is None:
        return None
    sec = int(_field(stamp, "sec", 0))
    nanosec = int(_field(stamp, "nanosec", 0))
    return sec * 1_000_000_000 + nanosec


def _field(value: Any, name: str, default: Any) -> Any:
    if value is None:
        return default
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)
