"""Compare two validation reports for regressions and coverage drift."""

from __future__ import annotations

from typing import Literal

from physlint.engine.runner import SEVERITY_RANK
from physlint.models.comparison import Comparison, CoverageDelta, RuleChange
from physlint.models.finding import CoverageSnapshot, Finding, Report, Severity


def compare_reports(baseline: Report, candidate: Report, *, fail_on: Severity = Severity.ERROR) -> Comparison:
    baseline_findings = _indexed(baseline)
    candidate_findings = _indexed(candidate)
    new_keys = [key for key in candidate_findings if key not in baseline_findings]
    resolved_keys = [key for key in baseline_findings if key not in candidate_findings]
    persistent_keys = [key for key in candidate_findings if key in baseline_findings]
    new_findings = [candidate_findings[key] for key in new_keys]
    resolved_findings = [baseline_findings[key] for key in resolved_keys]
    persistent_findings = [candidate_findings[key] for key in persistent_keys]
    rule_changes = _rule_changes(baseline, candidate)
    coverage = _coverage_delta(baseline.coverage, candidate.coverage)
    threshold = SEVERITY_RANK[fail_on]
    blocking_new = any(SEVERITY_RANK[item.severity] >= threshold for item in new_findings)
    blocking_new |= candidate.summary.errored > baseline.summary.errored
    blocking_resolved = any(SEVERITY_RANK[item.severity] >= threshold for item in resolved_findings)
    status: Literal["unchanged", "improved", "regressed", "changed"]
    if blocking_new:
        status = "regressed"
    elif not new_findings and not resolved_findings and not rule_changes and _coverage_unchanged(coverage):
        status = "unchanged"
    elif (blocking_resolved and not blocking_new) or (not new_findings and resolved_findings):
        status = "improved"
    else:
        status = "changed"
    return Comparison(
        status=status,
        baseline_dataset=baseline.dataset,
        candidate_dataset=candidate.dataset,
        baseline_fingerprint=baseline.source_fingerprint,
        candidate_fingerprint=candidate.source_fingerprint,
        baseline_status=baseline.status,
        candidate_status=candidate.status,
        new_findings=new_findings,
        resolved_findings=resolved_findings,
        persistent_findings=persistent_findings,
        rule_changes=rule_changes,
        coverage=coverage,
        baseline_coverage=baseline.coverage,
        candidate_coverage=candidate.coverage,
    )


def _indexed(report: Report) -> dict[tuple[str, str], Finding]:
    items: dict[tuple[str, str], Finding] = {}
    for result in report.results:
        for item in result.findings:
            items[(item.rule_id, item.fingerprint)] = item
    return items


def _rule_changes(baseline: Report, candidate: Report) -> list[RuleChange]:
    before = {result.rule_id: result.status.value for result in baseline.results}
    after = {result.rule_id: result.status.value for result in candidate.results}
    changes = []
    for rule_id in sorted(set(before) | set(after)):
        left = before.get(rule_id, "absent")
        right = after.get(rule_id, "absent")
        if left != right:
            changes.append(RuleChange(rule_id=rule_id, before=left, after=right))
    return changes


def _coverage_delta(before: CoverageSnapshot | None, after: CoverageSnapshot | None) -> CoverageDelta | None:
    if before is None or after is None:
        return None
    added_tasks = sorted(set(after.tasks) - set(before.tasks))
    removed_tasks = sorted(set(before.tasks) - set(after.tasks))
    task_count_changes = {
        task: {"before": before.tasks[task], "after": after.tasks[task]}
        for task in sorted(set(before.tasks) & set(after.tasks))
        if before.tasks[task] != after.tasks[task]
    }
    return CoverageDelta(
        episodes_before=before.episodes,
        episodes_after=after.episodes,
        frames_before=before.frames,
        frames_after=after.frames,
        messages_before=before.messages,
        messages_after=after.messages,
        added_streams=sorted(set(after.streams) - set(before.streams)),
        removed_streams=sorted(set(before.streams) - set(after.streams)),
        added_tasks=added_tasks,
        removed_tasks=removed_tasks,
        task_count_changes=task_count_changes,
    )


def _coverage_unchanged(delta: CoverageDelta | None) -> bool:
    if delta is None:
        return True
    return (
        delta.episodes_before == delta.episodes_after
        and delta.frames_before == delta.frames_after
        and delta.messages_before == delta.messages_after
        and not delta.added_streams
        and not delta.removed_streams
        and not delta.added_tasks
        and not delta.removed_tasks
        and not delta.task_count_changes
    )
