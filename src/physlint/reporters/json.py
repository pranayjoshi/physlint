"""Atomic JSON report writer."""

from __future__ import annotations

from pathlib import Path

from physlint.models.finding import Report
from physlint.reporters.atomic import write_atomic_text


def write_json_report(report: Report, path: Path) -> Path:
    return write_atomic_text(path, report.model_dump_json(indent=2) + "\n")
