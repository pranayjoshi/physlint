"""Build the public Observatory catalog from committed sanitized summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
LEROBOT_SUMMARY = ROOT / "validation" / "reports" / "real-data-2026-08-24" / "summary.json"
MCAP_SUMMARY = ROOT / "validation" / "reports" / "mcap-ros2-2026-08-26" / "summary.json"
DEFAULT_OUTPUT = ROOT / "observatory" / "data" / "observations.json"

NAMES = {
    "panda": "Robomimic CAN PH",
    "rover": "Scout Earth Rover Mini",
    "so101": "SVLA SO-101 Pick & Place",
    "sentinel": "Sentinel Demo 09",
}


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"unsupported validation summary: {path}")
    return payload


def build(output: Path = DEFAULT_OUTPUT) -> None:
    lerobot = load(LEROBOT_SUMMARY)
    mcap = load(MCAP_SUMMARY)
    observations: list[dict[str, Any]] = []
    for row in lerobot["results"]:
        if row["corruption"] is not None:
            continue
        observations.append(
            {
                "id": row["id"],
                "name": NAMES[row["id"]],
                "source": row["repo_id"],
                "robot": row["robot"],
                "profile": "LeRobot",
                "provenance": "Public",
                "scale": f"{row['episodes']} eps · {row['frames'] / 1000:.1f}k frames",
                "checks": row["applicable_rules"],
                "findings": row["findings"],
                "status": "Passed" if row["status"] == "passed" else "Issues found",
                "sourceUrl": f"https://huggingface.co/datasets/{row['repo_id']}",
                "reportPath": f"real-data-2026-08-24/{row['artifact']}",
                "revision": row["revision"],
            }
        )
    for row in mcap["results"]:
        is_public = row["provenance"] == "public"
        observations.append(
            {
                "id": row["id"],
                "name": row["title"],
                "source": "foxglove/mcap conformance suite" if is_public else row["source_revision"],
                "robot": "Generic channel" if row["profile"] == "generic" else "ROS 2 fixture",
                "profile": "MCAP" if row["profile"] == "generic" else "ROS 2",
                "provenance": "Public" if is_public else "Controlled",
                "scale": f"{row['messages']} messages",
                "checks": row["rules_checked"],
                "findings": row["findings"],
                "status": "Passed" if row["status"] == "passed" else "Issues found",
                "sourceUrl": (
                    "https://github.com/foxglove/mcap/tree/main/tests/conformance/data/TenMessages"
                    if is_public
                    else None
                ),
                "reportPath": f"mcap-ros2-2026-08-26/{row['artifact']}",
                "revision": row["source_revision"],
            }
        )
    payload = {
        "schema_version": 1,
        "generated_from": [
            str(LEROBOT_SUMMARY.relative_to(ROOT)),
            str(MCAP_SUMMARY.relative_to(ROOT)),
        ],
        "observations": observations,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
