from __future__ import annotations

import json

from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.reporters.html import write_html_report
from physlint.reporters.junit import write_junit_report
from physlint.reporters.sarif import write_sarif_report


def test_junit_sarif_and_html_reports_are_written(dataset_factory, tmp_path):
    timestamps = [0, 0, 2 / 30, 3 / 30, 4 / 30, 5 / 30] * 2
    report = run_validation(discover(dataset_factory(timestamps=timestamps)), Config())
    junit = write_junit_report(report, tmp_path / "report.xml")
    sarif_path = write_sarif_report(report, tmp_path / "report.sarif")
    html = write_html_report(report, tmp_path / "report.html")
    xml = junit.read_text(encoding="utf-8")
    assert "<testsuite" in xml
    assert "temporal.monotonic" in xml
    assert "<failure" in xml
    payload = json.loads(sarif_path.read_text(encoding="utf-8"))
    assert payload["version"] == "2.1.0"
    assert payload["runs"][0]["results"]
    html_text = html.read_text(encoding="utf-8")
    assert "FAIL" in html_text
    assert "Coverage" in html_text
    assert "<img" not in html_text
