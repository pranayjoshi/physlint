"""Human- and machine-readable reporters."""

from datetime import UTC
from pathlib import Path

from physlint.config import Config
from physlint.models.finding import Report
from physlint.reporters.html import write_html_report
from physlint.reporters.json import write_json_report
from physlint.reporters.junit import write_junit_report
from physlint.reporters.sarif import write_sarif_report


def write_configured_reports(
    report: Report,
    settings: Config,
    *,
    json_output: Path | None = None,
    junit_output: Path | None = None,
    sarif_output: Path | None = None,
    html_output: Path | None = None,
) -> list[Path]:
    written: list[Path] = []
    stamp = report.started_at.astimezone(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    directory = Path(settings.reports.output_dir)
    if json_output is not None:
        written.append(write_json_report(report, json_output))
    elif settings.reports.json_enabled:
        written.append(write_json_report(report, directory / f"{stamp}.json"))
    if junit_output is not None:
        written.append(write_junit_report(report, junit_output))
    elif settings.reports.junit:
        written.append(write_junit_report(report, directory / f"{stamp}.junit.xml"))
    if sarif_output is not None:
        written.append(write_sarif_report(report, sarif_output))
    elif settings.reports.sarif:
        written.append(write_sarif_report(report, directory / f"{stamp}.sarif"))
    if html_output is not None:
        written.append(write_html_report(report, html_output))
    elif settings.reports.html:
        written.append(write_html_report(report, directory / f"{stamp}.html"))
    return written
