"""Build the public Observatory catalog from committed sanitized summaries."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from physlint.api import load_report
from physlint.engine.compare import compare_reports
from physlint.models.finding import Severity

ROOT = Path(__file__).resolve().parents[1]
LEROBOT_SUMMARY = ROOT / "validation" / "reports" / "real-data-2026-08-24" / "summary.json"
MCAP_SUMMARY = ROOT / "validation" / "reports" / "mcap-ros2-2026-08-26" / "summary.json"
SURVEY_SUMMARY = ROOT / "validation" / "reports" / "lerobot-survey-2026-08-30" / "summary.json"
REPORT_ROOT = ROOT / "validation" / "reports"
DEFAULT_OUTPUT = ROOT / "observatory" / "data" / "observations.json"
DEFAULT_COMPARISONS = ROOT / "observatory" / "data" / "comparisons.json"

NAMES = {
    "panda": "Robomimic CAN PH",
    "rover": "Scout Earth Rover Mini",
    "so101": "SVLA SO-101 Pick & Place",
    "sentinel": "Sentinel Demo 09",
}

COMPARISON_CASES = [
    {
        "id": "panda-nan",
        "title": "Controlled NaN injection",
        "baseline": "real-data-2026-08-24/clean-panda.json",
        "candidate": "real-data-2026-08-24/corruption-nan.json",
    },
    {
        "id": "panda-reordered",
        "title": "Controlled timestamp reorder",
        "baseline": "real-data-2026-08-24/clean-panda.json",
        "candidate": "real-data-2026-08-24/corruption-reordered.json",
    },
    {
        "id": "panda-truncated",
        "title": "Controlled source-row deletion",
        "baseline": "real-data-2026-08-24/clean-panda.json",
        "candidate": "real-data-2026-08-24/corruption-truncated.json",
    },
    {
        "id": "ros2-joint-state-corruption",
        "title": "Controlled ROS 2 cadence and dimension drift",
        "baseline": "mcap-ros2-2026-08-26/ros2-joint-state-clean.json",
        "candidate": "mcap-ros2-2026-08-26/ros2-joint-state-corrupt.json",
    },
]


def load(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"unsupported validation summary: {path}")
    return payload


def _scale(episodes: int | None, frames: int | None) -> str:
    if not episodes and not frames:
        return "unparsed"
    if frames and frames >= 1000:
        return f"{episodes or 0} eps · {frames / 1000:.1f}k frames"
    return f"{episodes or 0} eps · {frames or 0} frames"


def build(output: Path = DEFAULT_OUTPUT, comparisons_output: Path = DEFAULT_COMPARISONS) -> None:
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
                "scale": _scale(row["episodes"], row["frames"]),
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
                "source": row.get("source_name") or row["source_revision"],
                "robot": row.get("robot") or ("Generic channel" if row["profile"] == "generic" else "ROS 2 fixture"),
                "profile": "MCAP" if row["profile"] == "generic" else "ROS 2",
                "provenance": "Public" if is_public else "Controlled",
                "scale": f"{row['messages']} messages",
                "checks": row["rules_checked"],
                "findings": row["findings"],
                "status": "Passed" if row["status"] == "passed" else "Issues found",
                "sourceUrl": row.get("source_page") if is_public else None,
                "reportPath": f"mcap-ros2-2026-08-26/{row['artifact']}",
                "revision": row["source_revision"],
            }
        )
    generated_from = [
        str(LEROBOT_SUMMARY.relative_to(ROOT)),
        str(MCAP_SUMMARY.relative_to(ROOT)),
    ]
    if SURVEY_SUMMARY.is_file():
        survey = load(SURVEY_SUMMARY)
        generated_from.append(str(SURVEY_SUMMARY.relative_to(ROOT)))
        for row in survey["results"]:
            if row.get("kind") != "check" or not row.get("artifact"):
                continue
            observations.append(
                {
                    "id": row["id"],
                    "name": row.get("title") or row["id"],
                    "source": row["repo_id"],
                    "robot": row.get("robot") or "unspecified",
                    "profile": "LeRobot",
                    "provenance": "Survey",
                    "scale": _scale(row.get("episodes"), row.get("frames")),
                    "checks": row.get("applicable_rules") or 0,
                    "findings": row.get("findings") or 0,
                    "status": "Passed" if row["status"] == "passed" else "Issues found",
                    "sourceUrl": f"https://huggingface.co/datasets/{row['repo_id']}",
                    "reportPath": f"lerobot-survey-2026-08-30/{row['artifact']}",
                    "revision": row["revision"],
                }
            )
    payload = {
        "schema_version": 1,
        "generated_from": generated_from,
        "observations": observations,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    comparisons_output.write_text(json.dumps(_comparisons(), indent=2) + "\n", encoding="utf-8")


def _comparisons() -> dict[str, Any]:
    rows = []
    for case in COMPARISON_CASES:
        comparison = compare_reports(
            load_report(REPORT_ROOT / case["baseline"]),
            load_report(REPORT_ROOT / case["candidate"]),
            fail_on=Severity.ERROR,
        )
        rows.append(
            {
                "id": case["id"],
                "title": case["title"],
                "status": comparison.status,
                "newFindings": len(comparison.new_findings),
                "resolvedFindings": len(comparison.resolved_findings),
                "persistentFindings": len(comparison.persistent_findings),
                "newRules": sorted({item.rule_id for item in comparison.new_findings}),
                "baselineReportPath": case["baseline"],
                "candidateReportPath": case["candidate"],
            }
        )
    return {
        "schema_version": 1,
        "generated_from": [str(REPORT_ROOT.relative_to(ROOT))],
        "comparisons": rows,
    }


if __name__ == "__main__":
    build()
