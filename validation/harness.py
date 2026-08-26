"""Run the pinned public-data release gate and emit sanitized evidence."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import Report, RuleStatus

ROOT = Path(__file__).resolve().parent
DEFAULT_MANIFEST = ROOT / "manifest.yaml"
DEFAULT_OUTPUT = ROOT / "reports" / "real-data-2026-08-24"
DEFAULT_WORK = ROOT / ".work"


def load_manifest(path: Path) -> dict[str, Any]:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise ValueError(f"unsupported validation manifest: {path}")
    if not isinstance(payload.get("datasets"), list) or not isinstance(payload.get("corruptions"), list):
        raise ValueError(f"manifest must contain dataset and corruption lists: {path}")
    items = [*payload["datasets"], *payload["corruptions"]]
    if not all(isinstance(item, dict) for item in items):
        raise ValueError("dataset and corruption entries must be mappings")
    identifiers = [item.get("id") for item in items]
    if not all(isinstance(value, str) and re.fullmatch(r"[a-z0-9_-]+", value) for value in identifiers):
        raise ValueError("dataset and corruption IDs must contain only lowercase letters, numbers, _ or -")
    return payload


def parse_root_overrides(values: Iterable[str]) -> dict[str, Path]:
    overrides: dict[str, Path] = {}
    for value in values:
        identifier, separator, raw_path = value.partition("=")
        if not separator or not identifier or not raw_path:
            raise ValueError(f"dataset root must be ID=PATH, received {value!r}")
        path = Path(raw_path).expanduser().resolve()
        if not path.is_dir():
            raise ValueError(f"dataset root does not exist: {path}")
        overrides[identifier] = path
    return overrides


def download_dataset(record: dict[str, Any], cache_dir: Path | None) -> Path:
    command = [
        "hf",
        "download",
        str(record["repo_id"]),
        "--repo-type",
        "dataset",
        "--revision",
        str(record["revision"]),
    ]
    if cache_dir is not None:
        command.extend(["--cache-dir", str(cache_dir)])
    completed = subprocess.run(command, check=True, capture_output=True, text=True)  # noqa: S603
    return parse_download_path(completed.stdout)


def parse_download_path(output: str) -> Path:
    """Accept both old bare-path and current human-readable ``hf`` output."""
    for raw_line in reversed(output.splitlines()):
        line = raw_line.strip()
        if line.startswith(("path:", "path=")):
            line = line[5:].strip()
        candidate = Path(line).expanduser()
        if candidate.is_dir():
            return candidate.resolve()
    raise RuntimeError(f"hf download did not return a dataset directory: {output}")


def copy_and_corrupt(source: Path, destination: Path, recipe: dict[str, Any]) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, symlinks=False)
    parquet = next(iter(sorted((destination / "data").glob("**/*.parquet"))), None)
    if parquet is None:
        raise ValueError(f"no Parquet source in {destination}")
    table = pq.read_table(parquet)
    mutation = recipe["mutation"]
    if mutation == "insert_nan":
        table = _insert_nan(table, str(recipe["stream"]), int(recipe["sample"]), int(recipe["dimension"]))
    elif mutation == "swap_timestamps":
        table = _swap_values(table, "timestamp", int(recipe["first"]), int(recipe["second"]))
    elif mutation == "delete_row":
        table = _delete_row(table, int(recipe["sample"]))
    else:
        raise ValueError(f"unknown corruption mutation: {mutation}")
    pq.write_table(table, parquet)


def _insert_nan(table: pa.Table, stream: str, sample: int, dimension: int) -> pa.Table:
    index = table.schema.get_field_index(stream)
    if index < 0:
        raise ValueError(f"stream is absent: {stream}")
    values = table.column(index).to_pylist()
    row = list(values[sample])
    row[dimension] = float("nan")
    values[sample] = row
    return table.set_column(index, table.schema.field(index), pa.array(values, type=table.schema.field(index).type))


def _swap_values(table: pa.Table, stream: str, first: int, second: int) -> pa.Table:
    index = table.schema.get_field_index(stream)
    if index < 0:
        raise ValueError(f"stream is absent: {stream}")
    values = table.column(index).to_pylist()
    values[first], values[second] = values[second], values[first]
    return table.set_column(index, table.schema.field(index), pa.array(values, type=table.schema.field(index).type))


def _delete_row(table: pa.Table, sample: int) -> pa.Table:
    if sample < 0 or sample >= table.num_rows:
        raise ValueError(f"sample index {sample} is outside a table with {table.num_rows} rows")
    indices = pa.array([index for index in range(table.num_rows) if index != sample], type=pa.int64())
    return table.take(indices)


def sanitized_report(report: Report, dataset: str, revision: str, canonical_path: str) -> Report:
    return report.model_copy(
        update={
            "dataset": dataset,
            "source_revision": revision,
            "dataset_path": canonical_path,
        }
    )


def assert_clean(report: Report, identifier: str) -> None:
    if report.status != "passed" or report.summary.findings or report.summary.errored:
        raise AssertionError(f"clean validation failed for {identifier}: {report.summary.model_dump()}")


def assert_corruption(report: Report, recipe: dict[str, Any]) -> None:
    statuses = {result.rule_id: result.status for result in report.results}
    for rule_id in recipe["expected_rules"]:
        if statuses.get(rule_id) != RuleStatus.FAILED:
            raise AssertionError(f"{recipe['id']} did not fail expected rule {rule_id}")
    for rule_id in recipe.get("forbidden_rules", []):
        if statuses.get(rule_id) == RuleStatus.FAILED:
            raise AssertionError(f"{recipe['id']} unexpectedly failed {rule_id}")


def write_report(report: Report, path: Path) -> str:
    payload = report.model_dump_json(indent=2) + "\n"
    path.write_text(payload, encoding="utf-8")
    return hashlib.sha256(payload.encode()).hexdigest()


def report_summary(
    report: Report,
    record: dict[str, Any],
    artifact: str,
    artifact_sha256: str,
    episodes: int,
    frames: int,
    corruption: str | None = None,
) -> dict[str, Any]:
    rule_time = sum(result.duration_ms for result in report.results) / 1000
    applicable = report.summary.passed + report.summary.failed
    baseline = float(record["baseline_rule_time_seconds"])
    return {
        "id": record["id"] if corruption is None else f"{record['id']}-{corruption}",
        "repo_id": record["repo_id"],
        "revision": record["revision"],
        "robot": record["robot"],
        "corruption": corruption,
        "episodes": episodes,
        "frames": frames,
        "status": report.status,
        "applicable_rules": applicable,
        "findings": report.summary.findings,
        "errored": report.summary.errored,
        "rule_time_seconds": round(rule_time, 3),
        "baseline_rule_time_seconds": baseline if corruption is None else None,
        "speedup": round(baseline / rule_time, 2) if corruption is None and rule_time else None,
        "artifact": artifact,
        "artifact_sha256": artifact_sha256,
    }


def write_summary(rows: list[dict[str, Any]], output: Path, run_id: str, version: str) -> None:
    clean = [row for row in rows if row["corruption"] is None]
    corruptions = [row for row in rows if row["corruption"] is not None]
    payload = {
        "schema_version": 1,
        "run_id": run_id,
        "physlint_version": version,
        "clean_datasets": len(clean),
        "clean_passed": sum(row["status"] == "passed" for row in clean),
        "episodes": sum(int(row["episodes"] or 0) for row in clean),
        "frames": sum(int(row["frames"] or 0) for row in clean),
        "controlled_corruptions": len(corruptions),
        "controlled_corruptions_detected": sum(row["status"] == "failed" for row in corruptions),
        "results": rows,
    }
    (output / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    fieldnames = list(rows[0])
    with (output / "summary.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def run(args: argparse.Namespace) -> None:
    manifest = load_manifest(args.manifest)
    overrides = parse_root_overrides(args.dataset_root)
    args.output.mkdir(parents=True, exist_ok=True)
    args.work.mkdir(parents=True, exist_ok=True)
    records = {str(item["id"]): item for item in manifest["datasets"]}
    roots: dict[str, Path] = {}
    summaries: list[dict[str, Any]] = []
    for identifier, record in records.items():
        root = overrides.get(identifier) or download_dataset(record, args.cache_dir)
        roots[identifier] = root
        dataset = discover(root)
        report = run_validation(dataset, Config())
        assert_clean(report, identifier)
        safe = sanitized_report(
            report,
            str(record["repo_id"]),
            str(record["revision"]),
            f"hf://datasets/{record['repo_id']}@{record['revision']}",
        )
        artifact = f"clean-{identifier}.json"
        digest = write_report(safe, args.output / artifact)
        row = report_summary(
            safe,
            record,
            artifact,
            digest,
            len(dataset.inventory.episodes),
            dataset.inventory.total_frames,
        )
        summaries.append(row)

    for recipe in manifest["corruptions"]:
        base = records[str(recipe["base_dataset"])]
        destination = args.work / f"corruption-{recipe['id']}"
        copy_and_corrupt(roots[str(recipe["base_dataset"])], destination, recipe)
        dataset = discover(destination)
        report = run_validation(dataset, Config())
        assert_corruption(report, recipe)
        safe = sanitized_report(
            report,
            f"{base['repo_id']} [corruption:{recipe['id']}]",
            str(base["revision"]),
            f"generated://{recipe['id']}@{base['revision']}",
        )
        artifact = f"corruption-{recipe['id']}.json"
        digest = write_report(safe, args.output / artifact)
        row = report_summary(
            safe,
            base,
            artifact,
            digest,
            len(dataset.inventory.episodes),
            dataset.inventory.total_frames,
            str(recipe["id"]),
        )
        summaries.append(row)
    write_summary(summaries, args.output, str(manifest["run_id"]), str(manifest["physlint_version"]))


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    result.add_argument("--work", type=Path, default=DEFAULT_WORK)
    result.add_argument("--cache-dir", type=Path)
    result.add_argument(
        "--dataset-root",
        action="append",
        default=[],
        metavar="ID=PATH",
        help="Use an existing pinned snapshot instead of invoking hf download; repeatable.",
    )
    return result


if __name__ == "__main__":
    run(parser().parse_args())
