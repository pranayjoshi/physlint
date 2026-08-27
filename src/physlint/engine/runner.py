"""Deterministic rule execution with timing and exception isolation."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from physlint._version import __version__
from physlint.adapters.base import AdapterError
from physlint.config import Config
from physlint.engine.planner import plan_rules
from physlint.models.dataset import DatasetView
from physlint.models.finding import Report, RuleResult, RuleStatus, RunSummary, Severity
from physlint.models.rule import RuleNotApplicable

SEVERITY_RANK = {
    Severity.NOTICE: 0,
    Severity.WARNING: 1,
    Severity.ERROR: 2,
    Severity.CRITICAL: 3,
}


def run_validation(
    dataset: DatasetView,
    config: Config,
    *,
    clock: Callable[[], datetime] | None = None,
) -> Report:
    clock = clock or (lambda: datetime.now(UTC))
    started = clock()
    results: list[RuleResult] = []
    for planned in plan_rules(dataset, config):
        metadata = planned.rule.metadata
        if planned.not_run_reason:
            results.append(
                RuleResult(
                    rule_id=metadata.id,
                    rule_version=metadata.version,
                    status=RuleStatus.NOT_RUN,
                    duration_ms=0,
                    reason=planned.not_run_reason,
                )
            )
            continue
        before = time.perf_counter()
        try:
            findings = planned.rule.run(dataset, planned.options, planned.severity)
            status = RuleStatus.FAILED if findings else RuleStatus.PASSED
            results.append(
                RuleResult(
                    rule_id=metadata.id,
                    rule_version=metadata.version,
                    status=status,
                    duration_ms=(time.perf_counter() - before) * 1000,
                    findings=findings,
                )
            )
        except RuleNotApplicable as exc:
            results.append(
                RuleResult(
                    rule_id=metadata.id,
                    rule_version=metadata.version,
                    status=RuleStatus.NOT_RUN,
                    duration_ms=(time.perf_counter() - before) * 1000,
                    reason=str(exc),
                )
            )
        except AdapterError as exc:
            results.append(
                RuleResult(
                    rule_id=metadata.id,
                    rule_version=metadata.version,
                    status=RuleStatus.ERRORED,
                    duration_ms=(time.perf_counter() - before) * 1000,
                    reason=f"AdapterError: {exc}",
                    error_kind="adapter",
                )
            )
        except Exception as exc:  # noqa: BLE001 - isolation is an engine responsibility
            results.append(
                RuleResult(
                    rule_id=metadata.id,
                    rule_version=metadata.version,
                    status=RuleStatus.ERRORED,
                    duration_ms=(time.perf_counter() - before) * 1000,
                    reason=f"{type(exc).__name__}: {exc}",
                    error_kind="rule",
                )
            )
    threshold = SEVERITY_RANK[Severity(config.fail_on)]
    all_findings = [finding for result in results for finding in result.findings]
    fails_contract = any(SEVERITY_RANK[finding.severity] >= threshold for finding in all_findings)
    fails_contract |= any(result.status == RuleStatus.ERRORED for result in results)
    summary = RunSummary(
        passed=sum(result.status == RuleStatus.PASSED for result in results),
        failed=sum(result.status == RuleStatus.FAILED for result in results),
        not_run=sum(result.status == RuleStatus.NOT_RUN for result in results),
        errored=sum(result.status == RuleStatus.ERRORED for result in results),
        findings=len(all_findings),
    )
    return Report(
        physlint_version=__version__,
        adapter=dataset.inventory.adapter,
        adapter_version=getattr(dataset, "version", "unknown"),
        dataset=dataset.inventory.name,
        source_revision=dataset.inventory.source_revision,
        dataset_path=str(dataset.root),
        source_fingerprint=source_fingerprint(dataset.root),
        source_fingerprint_method=(
            "file-content-sha256-v1" if dataset.root.is_file() else "metadata-and-file-stat-sha256-v1"
        ),
        configuration_digest=config.digest(),
        started_at=started,
        finished_at=clock(),
        status="failed" if fails_contract else "passed",
        results=results,
        summary=summary,
    )


def source_fingerprint(root: Path) -> str:
    """Hash metadata content and source-file size/mtime without reading all payload bytes."""
    digest = hashlib.sha256()
    if root.is_file():
        with root.open("rb") as handle:
            for block in iter(lambda: handle.read(1_048_576), b""):
                digest.update(block)
        return digest.hexdigest()
    metadata_paths = sorted((root / "meta").glob("**/*"))
    payload_paths = sorted((root / "data").glob("**/*.parquet")) + sorted((root / "videos").glob("**/*"))
    for path in metadata_paths:
        if not path.is_file():
            continue
        digest.update(str(path.relative_to(root)).encode())
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1_048_576), b""):
                digest.update(block)
    for path in payload_paths:
        if not path.is_file():
            continue
        stat = path.stat()
        record = [str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns]
        digest.update(json.dumps(record, separators=(",", ":")).encode())
    return digest.hexdigest()
