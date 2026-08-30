"""Self-contained local HTML report. Images and raw samples are never embedded."""

from __future__ import annotations

import html
from pathlib import Path

from physlint.models.finding import Finding, Report
from physlint.reporters.atomic import write_atomic_text


def write_html_report(report: Report, path: Path) -> Path:
    return write_atomic_text(path, render_html_report(report))


def render_html_report(report: Report) -> str:
    status = html.escape(report.status.upper())
    tone = "pass" if report.status == "passed" else "fail"
    findings = [item for result in report.results for item in result.findings]
    finding_blocks = "\n".join(_finding_html(item) for item in findings) or "<p class='empty'>No findings.</p>"
    incomplete = [result for result in report.results if result.reason]
    incomplete_html = ""
    if incomplete:
        rows = "".join(
            f"<li><code>{html.escape(result.rule_id)}</code> {html.escape(result.reason or '')}</li>"
            for result in incomplete
        )
        incomplete_html = f"<h2>Incomplete rules</h2><ul>{rows}</ul>"
    coverage_html = _coverage_html(report)
    suppressed_html = ""
    if report.suppressed:
        rows = "".join(
            f"<li><code>{html.escape(item.rule_id)}</code> accepted by {html.escape(item.author)}: "
            f"{html.escape(item.reason)}</li>"
            for item in report.suppressed
        )
        suppressed_html = f"<h2>Reviewed suppressions</h2><ul>{rows}</ul>"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8"/>
  <title>Physlint report — {html.escape(report.dataset)}</title>
  <style>
    body {{ font: 16px/1.5 ui-sans-serif, system-ui, sans-serif; margin: 0; background: #f4f1e8; color: #18211f; }}
    main {{ width: min(920px, calc(100% - 40px)); margin: 32px auto 64px; }}
    h1 {{ letter-spacing: -0.04em; }}
    .status {{ display: inline-block; padding: 4px 10px; font-weight: 700; }}
    .pass {{ background: #0c6f61; color: #f4f1e8; }}
    .fail {{ background: #c4412d; color: #fff; }}
    .meta, .finding {{ border: 1px solid #d5d0c2; background: #fff; padding: 14px 16px; margin: 12px 0; }}
    .sev-critical, .sev-error {{ border-left: 4px solid #c4412d; }}
    .sev-warning {{ border-left: 4px solid #c9a227; }}
    .sev-notice {{ border-left: 4px solid #0c6f61; }}
    code {{ font-family: ui-monospace, SFMono-Regular, monospace; font-size: 13px; }}
    .empty, .note {{ color: #61706c; }}
  </style>
</head>
<body>
<main>
  <p class="note">Physlint HTML report. Evidence only — not a safety certificate. Images are never embedded.</p>
  <h1>{html.escape(report.dataset)}</h1>
  <p><span class="status {tone}">{status}</span></p>
  <div class="meta">
    <div>Adapter: <code>{html.escape(report.adapter)}</code> {html.escape(report.adapter_version)}</div>
    <div>Source fingerprint: <code>{html.escape(report.source_fingerprint)}</code></div>
    <div>Rules: {report.summary.passed} passed, {report.summary.failed} failed,
      {report.summary.not_run} not run, {report.summary.errored} errored</div>
    <div>Findings: {report.summary.findings}</div>
  </div>
  {coverage_html}
  <h2>Findings</h2>
  {finding_blocks}
  {suppressed_html}
  {incomplete_html}
</main>
</body>
</html>
"""


def _finding_html(item: Finding) -> str:
    location = []
    if item.location.episode:
        location.append(item.location.episode)
    if item.location.stream:
        location.append(item.location.stream)
    if item.location.sample_index is not None:
        location.append(f"sample {item.location.sample_index}")
    where = f" ({html.escape(', '.join(location))})" if location else ""
    return (
        f"<article class='finding sev-{html.escape(item.severity.value)}'>"
        f"<div><code>{html.escape(item.rule_id)}</code> {html.escape(item.severity.value)}</div>"
        f"<p>{html.escape(item.message)}{where}</p>"
        f"<p class='note'>Remediation: {html.escape(item.remediation)}</p>"
        "</article>"
    )


def _coverage_html(report: Report) -> str:
    coverage = report.coverage
    if coverage is None:
        return ""
    tasks = ", ".join(f"{html.escape(name)}={count}" for name, count in coverage.tasks.items()) or "none"
    return (
        "<h2>Coverage</h2>"
        "<div class='meta'>"
        f"<div>Episodes: {coverage.episodes}</div>"
        f"<div>Frames: {coverage.frames if coverage.frames is not None else 'n/a'}</div>"
        f"<div>Streams: {html.escape(', '.join(coverage.streams))}</div>"
        f"<div>Tasks: {tasks}</div>"
        "<p class='note'>Coverage lists what is present. It is not a universal quality score.</p>"
        "</div>"
    )
