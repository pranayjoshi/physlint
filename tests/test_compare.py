from __future__ import annotations

from pathlib import Path

from physlint.api import compare_sources, load_report
from physlint.config import Config
from physlint.engine.compare import compare_reports
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import Severity

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "validation" / "reports" / "real-data-2026-08-24" / "clean-panda.json"
NAN = ROOT / "validation" / "reports" / "real-data-2026-08-24" / "corruption-nan.json"


def test_committed_reports_remain_loadable():
    report = load_report(CLEAN)
    assert report.status == "passed"
    assert report.coverage is None


def test_compare_detects_controlled_nan_regression():
    comparison = compare_reports(load_report(CLEAN), load_report(NAN), fail_on=Severity.ERROR)
    assert comparison.status == "regressed"
    assert comparison.new_findings
    assert comparison.new_findings[0].rule_id == "numeric.finite_values"
    assert not comparison.resolved_findings


def test_compare_clean_fixtures_are_unchanged(dataset_factory):
    first = run_validation(discover(dataset_factory()), Config())
    second = run_validation(discover(dataset_factory()), Config())
    comparison = compare_reports(first, second)
    assert comparison.status in {"unchanged", "changed"}
    assert not comparison.new_findings
    assert not comparison.resolved_findings
    assert comparison.coverage is not None
    assert comparison.coverage.episodes_before == comparison.coverage.episodes_after == 2


def test_compare_sources_accepts_json_reports():
    comparison = compare_sources(CLEAN, NAN)
    assert comparison.status == "regressed"
