"""Deterministic rule execution with timing, caching, and exception isolation."""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

from physlint._version import __version__
from physlint.adapters.base import AdapterError
from physlint.config import Config
from physlint.engine.cache import RuleCache
from physlint.engine.planner import PlannedRule, plan_rules
from physlint.models.dataset import DatasetView
from physlint.models.finding import (
    CacheSummary,
    CoverageSnapshot,
    Report,
    RuleResult,
    RuleStatus,
    RunSummary,
    Severity,
)
from physlint.models.rule import Rule, RuleNotApplicable
from physlint.plugins import load_plugin_rules

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
    extra_rules: Sequence[Rule] | None = None,
) -> Report:
    clock = clock or (lambda: datetime.now(UTC))
    started = clock()
    plugins = list(extra_rules) if extra_rules is not None else load_plugin_rules(config.plugins)
    fingerprint = source_fingerprint(dataset.root)
    cache = RuleCache(
        config.cache,
        source_fingerprint=fingerprint,
        dataset_path=str(dataset.root),
        physlint_version=__version__,
    )
    results: list[RuleResult] = []
    for planned in plan_rules(dataset, config, extra=plugins):
        results.append(_run_planned(dataset, planned, cache))
    fails_contract = contract_failed(results, Severity(config.fail_on))
    return Report(
        physlint_version=__version__,
        adapter=dataset.inventory.adapter,
        adapter_version=getattr(dataset, "version", "unknown"),
        dataset=dataset.inventory.name,
        source_revision=dataset.inventory.source_revision,
        dataset_path=str(dataset.root),
        source_fingerprint=fingerprint,
        source_fingerprint_method=(
            "file-content-sha256-v1" if dataset.root.is_file() else "metadata-and-file-stat-sha256-v1"
        ),
        configuration_digest=config.digest(),
        started_at=started,
        finished_at=clock(),
        status="failed" if fails_contract else "passed",
        results=results,
        summary=summarize(results),
        coverage=coverage_snapshot(dataset),
        cache=CacheSummary(
            used=cache.enabled,
            hits=cache.hits,
            misses=cache.misses,
            directory=str(cache.directory) if cache.directory is not None else None,
        ),
        plugins=[rule.metadata.id for rule in plugins],
    )


def _run_planned(dataset: DatasetView, planned: PlannedRule, cache: RuleCache) -> RuleResult:
    metadata = planned.rule.metadata
    if planned.not_run_reason:
        return RuleResult(
            rule_id=metadata.id,
            rule_version=metadata.version,
            status=RuleStatus.NOT_RUN,
            duration_ms=0,
            reason=planned.not_run_reason,
        )
    cached = cache.get(planned)
    if cached is not None:
        return cached
    before = time.perf_counter()
    try:
        findings = planned.rule.run(dataset, planned.options, planned.severity)
        result = RuleResult(
            rule_id=metadata.id,
            rule_version=metadata.version,
            status=RuleStatus.FAILED if findings else RuleStatus.PASSED,
            duration_ms=(time.perf_counter() - before) * 1000,
            findings=findings,
        )
        cache.put(planned, result)
        return result
    except RuleNotApplicable as exc:
        return RuleResult(
            rule_id=metadata.id,
            rule_version=metadata.version,
            status=RuleStatus.NOT_RUN,
            duration_ms=(time.perf_counter() - before) * 1000,
            reason=str(exc),
        )
    except AdapterError as exc:
        return RuleResult(
            rule_id=metadata.id,
            rule_version=metadata.version,
            status=RuleStatus.ERRORED,
            duration_ms=(time.perf_counter() - before) * 1000,
            reason=f"AdapterError: {exc}",
            error_kind="adapter",
        )
    except Exception as exc:  # noqa: BLE001 - isolation is an engine responsibility
        return RuleResult(
            rule_id=metadata.id,
            rule_version=metadata.version,
            status=RuleStatus.ERRORED,
            duration_ms=(time.perf_counter() - before) * 1000,
            reason=f"{type(exc).__name__}: {exc}",
            error_kind="rule",
        )


def summarize(results: list[RuleResult]) -> RunSummary:
    findings = sum(len(result.findings) for result in results)
    return RunSummary(
        passed=sum(result.status == RuleStatus.PASSED for result in results),
        failed=sum(result.status == RuleStatus.FAILED for result in results),
        not_run=sum(result.status == RuleStatus.NOT_RUN for result in results),
        errored=sum(result.status == RuleStatus.ERRORED for result in results),
        findings=findings,
    )


def contract_failed(results: list[RuleResult], fail_on: Severity) -> bool:
    threshold = SEVERITY_RANK[fail_on]
    findings = [finding for result in results for finding in result.findings]
    if any(SEVERITY_RANK[finding.severity] >= threshold for finding in findings):
        return True
    return any(result.status == RuleStatus.ERRORED for result in results)


def coverage_snapshot(dataset: DatasetView) -> CoverageSnapshot:
    inventory = dataset.inventory
    tasks: dict[str, int] = {}
    lengths: list[int] = []
    for episode in inventory.episodes:
        lengths.append(episode.length)
        labels = episode.tasks or ["(unlabeled)"]
        for task in labels:
            tasks[task] = tasks.get(task, 0) + 1
    return CoverageSnapshot(
        episodes=len(inventory.episodes),
        frames=inventory.total_frames,
        messages=inventory.total_messages,
        streams=[stream.key for stream in inventory.streams],
        tasks=dict(sorted(tasks.items())),
        length_min=min(lengths) if lengths else None,
        length_max=max(lengths) if lengths else None,
        robot_type=inventory.robot_type,
        fps=inventory.fps,
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
