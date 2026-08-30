"""Run the LeRobot compatibility survey without changing the release gate."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

import yaml

from physlint.adapters.base import AdapterError
from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import Report
from validation.harness import parse_root_overrides, sanitized_report, write_report

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "survey_manifest.yaml"
DEFAULT_OUTPUT = ROOT / "reports" / "lerobot-survey-2026-08-30"
DEFAULT_WORK = ROOT / ".work" / "survey"
REVISION_RE = re.compile(r"^[0-9a-f]{40}$")
ID_RE = re.compile(r"^[a-z0-9_-]+$")


def load_survey_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"unsupported survey manifest: {path}")
    if payload.get("tier") != "compatibility-survey":
        raise ValueError("survey manifest must declare tier: compatibility-survey")
    for key in ("datasets", "screens", "deferred", "skipped"):
        if not isinstance(payload.get(key), list):
            raise ValueError(f"survey manifest field {key!r} must be a list")
    identifiers: list[str] = []
    for item in [*payload["datasets"], *payload["screens"], *payload["deferred"]]:
        if not isinstance(item, dict):
            raise ValueError("survey entries must be mappings")
        identifier = item.get("id")
        if not isinstance(identifier, str) or not ID_RE.fullmatch(identifier):
            raise ValueError("survey IDs must contain only lowercase letters, numbers, _ or -")
        identifiers.append(identifier)
        revision = item.get("revision")
        if revision is not None and not (isinstance(revision, str) and REVISION_RE.fullmatch(revision)):
            raise ValueError(f"survey revision must be a 40-character SHA: {identifier}")
        if "repo_id" not in item:
            raise ValueError(f"survey entry {identifier} is missing repo_id")
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("survey IDs must be unique")
    for record in payload["datasets"]:
        if not record.get("cells"):
            raise ValueError(f"check dataset {record['id']} must declare diversity cells")
    for record in payload["screens"]:
        if not record.get("expected_error") or not record.get("reason"):
            raise ValueError(f"screen {record['id']} must declare expected_error and reason")
    for record in payload["deferred"]:
        if not record.get("reason"):
            raise ValueError(f"deferred entry {record['id']} must declare a reason")
    for record in payload["skipped"]:
        if not isinstance(record, dict) or not record.get("repo_id") or not record.get("reason"):
            raise ValueError("skipped entries must include repo_id and reason")
    return payload


def download_snapshot(record: dict[str, Any], destination: Path, files: list[str] | None = None) -> Path:
    destination.mkdir(parents=True, exist_ok=True)
    command = [
        "hf",
        "download",
        str(record["repo_id"]),
        "--repo-type",
        "dataset",
        "--revision",
        str(record["revision"]),
        "--local-dir",
        str(destination),
    ]
    if files:
        command.extend(files)
    include = record.get("include")
    if include:
        command.extend(["--include", str(include)])
    subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    return destination


def resolve_source(record: dict[str, Any], root: Path) -> Path:
    subdir = record.get("source_subdir")
    if subdir:
        source = root / str(subdir)
        if not source.is_dir():
            raise FileNotFoundError(f"expected nested suite at {source}")
        return source
    return root


def finding_tally(report: Report) -> dict[str, int]:
    counts: dict[str, int] = {}
    for result in report.results:
        if result.findings:
            counts[result.rule_id] = len(result.findings)
    return counts


def summarize_check(
    record: dict[str, Any],
    report: Report | None,
    *,
    artifact: str | None,
    artifact_sha256: str | None,
    episodes: int | None,
    frames: int | None,
    error: str | None = None,
) -> dict[str, Any]:
    applicable = 0
    rule_time = None
    tally: dict[str, int] = {}
    status = "errored"
    findings = 0
    errored = 1 if error else 0
    if report is not None:
        applicable = report.summary.passed + report.summary.failed
        rule_time = round(sum(result.duration_ms for result in report.results) / 1000, 3)
        tally = finding_tally(report)
        status = report.status
        findings = report.summary.findings
        errored = report.summary.errored
    return {
        "id": record["id"],
        "kind": "check",
        "title": record.get("title") or record["id"],
        "repo_id": record["repo_id"],
        "revision": record["revision"],
        "robot": record.get("robot"),
        "fps": record.get("fps"),
        "cells": list(record.get("cells") or []),
        "status": status,
        "episodes": episodes,
        "frames": frames,
        "applicable_rules": applicable,
        "findings": findings,
        "errored": errored,
        "finding_rules": tally,
        "rule_time_seconds": rule_time,
        "error": error,
        "artifact": artifact,
        "artifact_sha256": artifact_sha256,
    }


def summarize_screen(
    record: dict[str, Any],
    *,
    status: str,
    observed_error: str | None,
    error: str | None = None,
) -> dict[str, Any]:
    return {
        "id": record["id"],
        "kind": "version-edge",
        "title": record.get("title") or record["id"],
        "repo_id": record["repo_id"],
        "revision": record["revision"],
        "cells": list(record.get("cells") or []),
        "status": status,
        "expected_error": record["expected_error"],
        "observed_error": observed_error,
        "error": error,
        "reason": record["reason"],
    }


def write_summary(payload: dict[str, Any], output: Path) -> None:
    (output / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    rows = payload["results"]
    if not rows:
        return
    fieldnames: list[str] = []
    for row in rows:
        for key in row:
            if key not in fieldnames:
                fieldnames.append(key)
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def selected(records: list[dict[str, Any]], only: set[str]) -> list[dict[str, Any]]:
    if not only:
        return records
    return [record for record in records if record["id"] in only]


def previous_results(output: Path) -> list[dict[str, Any]]:
    path = output / "summary.json"
    if not path.is_file():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    rows = payload.get("results")
    return rows if isinstance(rows, list) else []


def ordered_results(
    manifest: dict[str, Any],
    previous: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = {str(row["id"]): row for row in previous if isinstance(row, dict) and "id" in row}
    for row in updates:
        merged[str(row["id"])] = row
    return [
        merged[str(record["id"])] for record in [*manifest["datasets"], *manifest["screens"]] if record["id"] in merged
    ]


def run_check(
    record: dict[str, Any],
    root: Path,
    output: Path,
) -> dict[str, Any]:
    try:
        dataset = discover(resolve_source(record, root))
        report = run_validation(dataset, Config())
        safe = sanitized_report(
            report,
            str(record["repo_id"]),
            str(record["revision"]),
            f"hf://datasets/{record['repo_id']}@{record['revision']}",
        )
        artifact = f"check-{record['id']}.json"
        digest = write_report(safe, output / artifact)
        return summarize_check(
            record,
            safe,
            artifact=artifact,
            artifact_sha256=digest,
            episodes=len(dataset.inventory.episodes),
            frames=dataset.inventory.total_frames,
        )
    except Exception as exc:
        return summarize_check(
            record,
            None,
            artifact=None,
            artifact_sha256=None,
            episodes=None,
            frames=None,
            error=f"{type(exc).__name__}: {exc}",
        )


def run_screen(record: dict[str, Any], root: Path) -> dict[str, Any]:
    try:
        discover(root)
    except AdapterError as exc:
        message = str(exc)
        if record["expected_error"] not in message:
            return summarize_screen(
                record,
                status="errored",
                observed_error=message,
                error="unexpected adapter error",
            )
        return summarize_screen(record, status="rejected", observed_error=message)
    except Exception as exc:
        return summarize_screen(
            record,
            status="errored",
            observed_error=None,
            error=f"{type(exc).__name__}: {exc}",
        )
    return summarize_screen(
        record,
        status="errored",
        observed_error=None,
        error="adapter accepted an unsupported version",
    )


def run(args: argparse.Namespace) -> None:
    manifest = load_survey_manifest(args.manifest)
    overrides = parse_root_overrides(args.dataset_root)
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    only = set(args.only)
    previous = previous_results(args.output) if only else []
    updates: list[dict[str, Any]] = []

    def persist() -> None:
        results = ordered_results(manifest, previous, updates)
        checks = [row for row in results if row["kind"] == "check"]
        screens = [row for row in results if row["kind"] == "version-edge"]
        payload = {
            "schema_version": 1,
            "run_id": manifest["run_id"],
            "physlint_version": manifest["physlint_version"],
            "tier": "compatibility-survey",
            "claim": str(manifest["claim"]).strip(),
            "checked": len(checks),
            "checked_passed": sum(row["status"] == "passed" for row in checks),
            "checked_failed": sum(row["status"] == "failed" for row in checks),
            "checked_errored": sum(row["status"] == "errored" for row in checks),
            "screens": len(screens),
            "screens_rejected": sum(row["status"] == "rejected" for row in screens),
            "deferred": len(manifest["deferred"]),
            "skipped": len(manifest["skipped"]),
            "episodes": sum(int(row["episodes"] or 0) for row in checks),
            "frames": sum(int(row["frames"] or 0) for row in checks),
            "results": results,
        }
        write_summary(payload, args.output)
        digest = hashlib.sha256((args.output / "summary.json").read_bytes()).hexdigest()
        (args.output / "summary.sha256").write_text(digest + "\n", encoding="utf-8")

    for record in selected(manifest["datasets"], only):
        root = overrides.get(str(record["id"]))
        if root is None:
            root = download_snapshot(record, args.work / "datasets" / str(record["id"]))
        updates.append(run_check(record, root, args.output))
        persist()
        print(f"{record['id']}: {updates[-1]['status']} findings={updates[-1].get('findings')}", flush=True)

    for record in selected(manifest["screens"], only):
        root = overrides.get(str(record["id"]))
        if root is None:
            root = download_snapshot(
                record,
                args.work / "screens" / str(record["id"]),
                files=["meta/info.json"],
            )
        updates.append(run_screen(record, root))
        persist()
        print(f"{record['id']}: {updates[-1]['status']}", flush=True)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--work", type=Path, default=DEFAULT_WORK)
    result.add_argument(
        "--dataset-root",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="Use an existing snapshot instead of invoking hf download; repeatable.",
    )
    result.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit the run to one or more manifest IDs; repeatable.",
    )
    return result


if __name__ == "__main__":
    run(parser().parse_args())
