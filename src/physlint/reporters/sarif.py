"""SARIF 2.1.0 reporter for code-hosting annotations."""

from __future__ import annotations

import json
from pathlib import Path

from physlint.models.finding import Report, Severity
from physlint.reporters.atomic import write_atomic_text

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
LEVELS = {
    Severity.CRITICAL: "error",
    Severity.ERROR: "error",
    Severity.WARNING: "warning",
    Severity.NOTICE: "note",
}


def write_sarif_report(report: Report, path: Path) -> Path:
    rules = []
    seen: set[str] = set()
    results = []
    for result in report.results:
        if result.rule_id not in seen:
            seen.add(result.rule_id)
            title = result.findings[0].title if result.findings else result.rule_id
            rules.append(
                {
                    "id": result.rule_id,
                    "name": result.rule_id,
                    "shortDescription": {"text": title},
                    "helpUri": "https://github.com/pranayjoshi/physlint#what-physlint-checks",
                }
            )
        for item in result.findings:
            source = item.location
            uri = source.source or report.dataset_path
            logical = []
            if source.episode or source.stream:
                logical.append(
                    {"fullyQualifiedName": ".".join(part for part in (source.episode, source.stream) if part)}
                )
            entry: dict[str, object] = {
                "physicalLocation": {"artifactLocation": {"uri": uri}},
            }
            if logical:
                entry["logicalLocations"] = logical
            results.append(
                {
                    "ruleId": item.rule_id,
                    "level": LEVELS[item.severity],
                    "message": {"text": item.message},
                    "partialFingerprints": {"physlintFingerprint": item.fingerprint},
                    "locations": [entry],
                }
            )
    payload = {
        "$schema": SARIF_SCHEMA,
        "version": "2.1.0",
        "runs": [
            {
                "tool": {
                    "driver": {
                        "name": "Physlint",
                        "version": report.physlint_version,
                        "informationUri": "https://github.com/pranayjoshi/physlint",
                        "rules": rules,
                    }
                },
                "invocations": [
                    {
                        "executionSuccessful": report.summary.errored == 0,
                        "exitCode": 1 if report.status == "failed" else 0,
                    }
                ],
                "results": results,
            }
        ],
    }
    return write_atomic_text(path, json.dumps(payload, indent=2) + "\n")
