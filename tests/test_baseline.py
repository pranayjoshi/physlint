from __future__ import annotations

from datetime import date

from physlint.config import Config
from physlint.engine.baseline import apply_baseline, baseline_from_report
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import RuleStatus, Severity


def test_baseline_suppresses_only_matching_fingerprints(dataset_factory):
    timestamps = [0, 0, 2 / 30, 3 / 30, 4 / 30, 5 / 30] * 2
    report = run_validation(discover(dataset_factory(timestamps=timestamps)), Config())
    assert report.status == "failed"
    baseline = baseline_from_report(report, author="ada", reason="known recorder glitch", today=date(2026, 8, 30))
    reviewed = apply_baseline(report, baseline, fail_on=Severity.ERROR, today=date(2026, 8, 30))
    assert reviewed.status == "passed"
    assert reviewed.summary.findings == 0
    assert reviewed.suppressed
    assert all(item.author == "ada" for item in reviewed.suppressed)


def test_baseline_does_not_hide_new_instances_of_the_same_rule(dataset_factory):
    first = run_validation(
        discover(dataset_factory(timestamps=[0, 0, 2 / 30, 3 / 30, 4 / 30, 5 / 30] * 2)),
        Config(),
    )
    baseline = baseline_from_report(first, author="ada", reason="station A", today=date(2026, 8, 30))
    second = run_validation(
        discover(dataset_factory(timestamps=[0, 1 / 30, 0, 3 / 30, 4 / 30, 5 / 30] * 2)),
        Config(),
    )
    reviewed = apply_baseline(second, baseline, fail_on=Severity.ERROR, today=date(2026, 8, 30))
    assert reviewed.status == "failed"
    assert any(result.rule_id == "temporal.monotonic" for result in reviewed.results if result.findings)


def test_expired_suppression_is_ignored(dataset_factory):
    report = run_validation(
        discover(dataset_factory(timestamps=[0, 0, 2 / 30, 3 / 30, 4 / 30, 5 / 30] * 2)),
        Config(),
    )
    baseline = baseline_from_report(
        report,
        author="ada",
        reason="temporary",
        expires_at=date(2026, 1, 1),
        today=date(2026, 1, 1),
    )
    reviewed = apply_baseline(report, baseline, fail_on=Severity.ERROR, today=date(2026, 8, 30))
    assert reviewed.status == "failed"
    assert not reviewed.suppressed
    monotonic = next(result for result in reviewed.results if result.rule_id == "temporal.monotonic")
    assert monotonic.status == RuleStatus.FAILED
