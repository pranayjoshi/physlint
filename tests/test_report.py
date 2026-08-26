from __future__ import annotations

import json
from datetime import UTC, datetime

from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.reporters.json import write_json_report


def test_report_schema_and_atomic_writer(dataset_factory, tmp_path):
    fixed = datetime(2026, 8, 23, tzinfo=UTC)
    report = run_validation(discover(dataset_factory()), Config(), clock=lambda: fixed)
    destination = write_json_report(report, tmp_path / "nested" / "report.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["physlint_version"] == "0.1.0a1"
    assert payload["source_fingerprint_method"] == "metadata-and-file-stat-sha256-v1"
    assert not list(destination.parent.glob("*.tmp"))


def test_fingerprints_are_deterministic(dataset_factory):
    dataset = discover(dataset_factory(timestamps=[0, 0, 2 / 30, 3 / 30, 4 / 30, 5 / 30] * 2))
    first = run_validation(dataset, Config())
    second = run_validation(dataset, Config())
    first_fingerprints = [finding.fingerprint for result in first.results for finding in result.findings]
    second_fingerprints = [finding.fingerprint for result in second.results for finding in result.findings]
    assert first_fingerprints == second_fingerprints


def test_report_json_schema_is_versioned():
    from physlint.models.finding import Report

    schema = Report.model_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "1.0"
