"""Validate pinned public MCAP data and controlled ROS 2 recordings."""

from __future__ import annotations

import argparse
import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from mcap.writer import CompressionType
from mcap_ros2.writer import Writer as Ros2Writer

from physlint.config import Config, RuleSettings
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import Report, RuleStatus

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "mcap_manifest.yaml"
DEFAULT_OUTPUT = ROOT / "reports" / "mcap-ros2-2026-08-26"
DEFAULT_WORK = ROOT / ".work" / "mcap-ros2"

JOINT_STATE_MSGDEF = """\
std_msgs/Header header
string[] name
float64[] position
float64[] velocity
float64[] effort
================================================================================
MSG: std_msgs/Header
builtin_interfaces/Time stamp
string frame_id
================================================================================
MSG: builtin_interfaces/Time
int32 sec
uint32 nanosec
"""


def load_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"unsupported MCAP validation manifest: {path}")
    for key in ("public_recordings", "controlled_recordings"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"manifest field {key!r} must be a list")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(record: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(str(record["source_url"])) as response:  # noqa: S310
        destination.write_bytes(response.read())
    actual = sha256_file(destination)
    if actual != record["sha256"]:
        raise AssertionError(f"checksum mismatch for {record['id']}: {actual}")


def write_ros2_recording(path: Path, *, corrupt: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as output:
        writer = Ros2Writer(output, compression=CompressionType.NONE)
        schema = writer.register_msgdef("sensor_msgs/msg/JointState", JOINT_STATE_MSGDEF)
        times = [1_000_000_000, 1_100_000_000, 2_000_000_000 if corrupt else 1_200_000_000]
        for index, timestamp in enumerate(times):
            writer.write_message(
                topic="/joint_states",
                schema=schema,
                message={
                    "header": {
                        "stamp": {"sec": timestamp // 1_000_000_000, "nanosec": timestamp % 1_000_000_000},
                        "frame_id": "base_link",
                    },
                    "name": ["joint_1", "joint_2"],
                    "position": [float(index)] if corrupt and index == 1 else [float(index), 0.0],
                    "velocity": [0.0, 0.0],
                    "effort": [],
                },
                log_time=timestamp,
                publish_time=timestamp,
                sequence=index + 1,
            )
        writer.finish()


def config_for(record: dict[str, Any]) -> Config:
    settings: dict[str, RuleSettings] = {}
    if record.get("required_topics"):
        settings["ros2.required_topics"] = RuleSettings(options={"required_topics": record["required_topics"]})
    if record.get("topic_rates_hz"):
        settings["ros2.topic_gaps"] = RuleSettings(
            options={"topic_rates_hz": record["topic_rates_hz"], "max_gap_multiplier": 5.0}
        )
    return Config(profile=str(record["profile"]), rules=settings)


def assert_expected(report: Report, record: dict[str, Any]) -> None:
    if report.status != record["expected_status"]:
        raise AssertionError(f"{record['id']} returned {report.status}, expected {record['expected_status']}")
    statuses = {result.rule_id: result.status for result in report.results}
    for rule_id in record.get("expected_failed_rules", []):
        if statuses.get(rule_id) != RuleStatus.FAILED:
            raise AssertionError(f"{record['id']} did not fail expected rule {rule_id}")


def sanitized(report: Report, record: dict[str, Any], path: Path) -> Report:
    source_revision = record.get("source_revision") or f"recipe:{record['recipe']}"
    source_path = (
        f"github://foxglove/mcap@{source_revision}/{path.name}"
        if record.get("source_url")
        else f"generated://{record['recipe']}"
    )
    return report.model_copy(
        update={
            "dataset": str(record["title"]),
            "source_revision": source_revision,
            "dataset_path": source_path,
        }
    )


def result_row(report: Report, record: dict[str, Any], artifact: str) -> dict[str, Any]:
    failed = [result.rule_id for result in report.results if result.status == RuleStatus.FAILED]
    return {
        "id": record["id"],
        "title": record["title"],
        "format": record["format"],
        "profile": record["profile"],
        "provenance": "public" if record.get("source_url") else "controlled",
        "status": report.status,
        "messages": next((result for result in report.results if result.rule_id == "mcap.readable"), None) is not None,
        "rules_checked": report.summary.passed + report.summary.failed,
        "findings": report.summary.findings,
        "failed_rules": failed,
        "source_revision": report.source_revision,
        "source_fingerprint": report.source_fingerprint,
        "artifact": artifact,
    }


def run(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    records = [*manifest["public_recordings"], *manifest["controlled_recordings"]]
    for record in records:
        path = args.work / f"{record['id']}.mcap"
        if record.get("source_url"):
            if args.public_recording is not None:
                path = args.public_recording.resolve()
                if sha256_file(path) != record["sha256"]:
                    raise AssertionError(f"checksum mismatch for override {path}")
            else:
                download(record, path)
        else:
            write_ros2_recording(path, corrupt=str(record["recipe"]) != "joint_state_clean")
        dataset = discover(path, profile=str(record["profile"]))
        report = run_validation(dataset, config_for(record))
        assert_expected(report, record)
        safe = sanitized(report, record, path)
        artifact = f"{record['id']}.json"
        (args.output / artifact).write_text(safe.model_dump_json(indent=2) + "\n", encoding="utf-8")
        row = result_row(safe, record, artifact)
        row["messages"] = dataset.inventory.total_messages
        rows.append(row)
    summary = {
        "schema_version": 1,
        "run_id": manifest["run_id"],
        "physlint_version": manifest["physlint_version"],
        "recordings": len(rows),
        "public_recordings": sum(row["provenance"] == "public" for row in rows),
        "controlled_recordings": sum(row["provenance"] == "controlled" for row in rows),
        "expected_outcomes_verified": len(rows),
        "results": rows,
    }
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--work", type=Path, default=DEFAULT_WORK)
    result.add_argument(
        "--public-recording",
        type=Path,
        help="Use a checksum-verified local copy of the pinned public fixture instead of downloading it.",
    )
    return result


if __name__ == "__main__":
    run(parser().parse_args())
