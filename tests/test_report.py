from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from physlint import __version__
from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.cli import CliError, DemoResult, DoctorResult, WriteResult
from physlint.models.comparison import Comparison
from physlint.models.dataset import DatasetInventory
from physlint.models.finding import Report
from physlint.reporters.json import write_json_report


def test_report_schema_and_atomic_writer(dataset_factory, tmp_path):
    fixed = datetime(2026, 8, 23, tzinfo=UTC)
    report = run_validation(discover(dataset_factory()), Config(), clock=lambda: fixed)
    destination = write_json_report(report, tmp_path / "nested" / "report.json")
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "1.0"
    assert payload["physlint_version"] == __version__
    assert payload["source_fingerprint_method"] == "metadata-and-file-stat-sha256-v1"
    assert payload["coverage"]["episodes"] == 2
    assert "observation.state" in payload["coverage"]["streams"]
    assert not list(destination.parent.glob("*.tmp"))


def test_fingerprints_are_deterministic(dataset_factory):
    dataset = discover(dataset_factory(timestamps=[0, 0, 2 / 30, 3 / 30, 4 / 30, 5 / 30] * 2))
    first = run_validation(dataset, Config())
    second = run_validation(dataset, Config())
    first_fingerprints = [finding.fingerprint for result in first.results for finding in result.findings]
    second_fingerprints = [finding.fingerprint for result in second.results for finding in result.findings]
    assert first_fingerprints == second_fingerprints


def test_report_json_schema_is_versioned():
    schema = Report.model_json_schema()
    assert schema["properties"]["schema_version"]["const"] == "1.0"


def test_committed_json_schemas_are_current():
    root = Path(__file__).resolve().parents[1] / "schemas"
    expected = {
        "report-1.0.json": Report,
        "config-1.json": Config,
        "inventory-1.0.json": DatasetInventory,
        "comparison-1.0.json": Comparison,
        "error-1.0.json": CliError,
        "demo-1.0.json": DemoResult,
        "doctor-1.0.json": DoctorResult,
        "write-1.0.json": WriteResult,
    }
    for filename, model in expected.items():
        assert json.loads((root / filename).read_text(encoding="utf-8")) == model.model_json_schema(by_alias=True)
