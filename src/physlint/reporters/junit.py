"""JUnit XML reporter for CI systems."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from xml.dom import minidom

from physlint.models.finding import Report, RuleStatus
from physlint.reporters.atomic import write_atomic_text


def write_junit_report(report: Report, path: Path) -> Path:
    suites = ET.Element(
        "testsuites",
        {
            "name": "physlint",
            "tests": str(len(report.results)),
            "failures": str(report.summary.failed),
            "errors": str(report.summary.errored),
            "skipped": str(report.summary.not_run),
        },
    )
    suite = ET.SubElement(
        suites,
        "testsuite",
        {
            "name": report.dataset,
            "tests": str(len(report.results)),
            "failures": str(report.summary.failed),
            "errors": str(report.summary.errored),
            "skipped": str(report.summary.not_run),
        },
    )
    for result in report.results:
        case = ET.SubElement(
            suite,
            "testcase",
            {
                "classname": "physlint",
                "name": result.rule_id,
                "time": f"{result.duration_ms / 1000:.6f}",
            },
        )
        if result.status == RuleStatus.ERRORED:
            error = ET.SubElement(case, "error", {"message": result.reason or "rule error"})
            error.text = result.reason or ""
        elif result.status == RuleStatus.NOT_RUN:
            ET.SubElement(case, "skipped", {"message": result.reason or "not run"})
        elif result.status == RuleStatus.FAILED:
            lines = [item.message for item in result.findings] or [result.rule_id]
            failure = ET.SubElement(case, "failure", {"message": lines[0]})
            failure.text = "\n".join(lines)
    xml = _pretty(suites)
    return write_atomic_text(path, xml)


def _pretty(element: ET.Element) -> str:
    payload = ET.tostring(element, encoding="unicode")
    return minidom.parseString(payload).toprettyxml(indent="  ", encoding="utf-8").decode()
