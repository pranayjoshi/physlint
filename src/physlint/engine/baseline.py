"""Create and apply reviewed finding suppressions."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import yaml
from pydantic import ValidationError

from physlint.config import ConfigurationError
from physlint.engine.runner import contract_failed, summarize
from physlint.models.baseline import Baseline, Suppression
from physlint.models.finding import AppliedSuppression, Report, RuleStatus, Severity
from physlint.reporters.atomic import write_atomic_text


def load_baseline(path: Path) -> Baseline:
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(payload, dict):
            raise ConfigurationError("baseline root must be a mapping")
        return Baseline.model_validate(payload)
    except (OSError, yaml.YAMLError, ValidationError) as exc:
        raise ConfigurationError(f"invalid baseline {path}: {exc}") from exc


def write_baseline(baseline: Baseline, path: Path) -> Path:
    payload = yaml.safe_dump(baseline.model_dump(mode="json"), sort_keys=False, allow_unicode=True)
    return write_atomic_text(path, payload)


def baseline_from_report(
    report: Report,
    *,
    author: str,
    reason: str,
    expires_at: date | None = None,
    today: date | None = None,
) -> Baseline:
    accepted = today or datetime.now(UTC).date()
    suppressions = [
        Suppression(
            fingerprint=finding.fingerprint,
            rule_id=finding.rule_id,
            reason=reason,
            author=author,
            accepted_at=accepted,
            expires_at=expires_at,
        )
        for result in report.results
        for finding in result.findings
    ]
    return Baseline(
        created_at=accepted,
        author=author,
        dataset=report.dataset,
        source_fingerprint=report.source_fingerprint,
        reason=reason,
        suppressions=suppressions,
    )


def apply_baseline(
    report: Report,
    baseline: Baseline,
    *,
    fail_on: Severity = Severity.ERROR,
    today: date | None = None,
) -> Report:
    current = today or datetime.now(UTC).date()
    lookup = {(item.fingerprint, item.rule_id): item for item in baseline.suppressions}
    suppressed: list[AppliedSuppression] = []
    results = []
    for result in report.results:
        kept = []
        for finding in result.findings:
            item = lookup.get((finding.fingerprint, finding.rule_id))
            if item is None or (item.expires_at is not None and item.expires_at < current):
                kept.append(finding)
                continue
            suppressed.append(
                AppliedSuppression(
                    fingerprint=item.fingerprint,
                    rule_id=item.rule_id,
                    reason=item.reason,
                    author=item.author,
                    accepted_at=item.accepted_at.isoformat(),
                    expires_at=item.expires_at.isoformat() if item.expires_at else None,
                )
            )
        status = result.status
        if result.status == RuleStatus.FAILED and not kept:
            status = RuleStatus.PASSED
        results.append(result.model_copy(update={"findings": kept, "status": status}))
    return report.model_copy(
        update={
            "results": results,
            "summary": summarize(results),
            "status": "failed" if contract_failed(results, fail_on) else "passed",
            "suppressed": suppressed,
        }
    )
