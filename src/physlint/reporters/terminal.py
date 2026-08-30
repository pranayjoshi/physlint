"""Concise Rich terminal presentation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

from physlint.models.comparison import Comparison
from physlint.models.dataset import DatasetInventory
from physlint.models.finding import Report, Severity
from physlint.models.rule import RuleMetadata

SEVERITY_STYLE = {
    Severity.CRITICAL: "bold red",
    Severity.ERROR: "red",
    Severity.WARNING: "yellow",
    Severity.NOTICE: "cyan",
}


def render_report(report: Report, report_path: Path | None = None, console: Console | None = None) -> None:
    console = console or Console()
    style = "green" if report.status == "passed" else "bold red"
    console.print(f"Dataset: [bold]{report.dataset}[/bold]")
    console.print(f"Result: [{style}]{report.status.upper()}[/{style}]")
    console.print(
        f"Rules: {report.summary.passed} passed, {report.summary.failed} failed, "
        f"{report.summary.not_run} not run, {report.summary.errored} errored"
    )
    grouped = defaultdict(list)
    for result in report.results:
        for item in result.findings:
            grouped[item.severity].append(item)
    for severity in Severity:
        if not grouped[severity]:
            continue
        console.print(f"\n[{SEVERITY_STYLE[severity]}]{severity.value.title()}[/]")
        for item in grouped[severity]:
            location = ""
            if item.location.episode:
                location = f" ({item.location.episode}"
                if item.location.stream:
                    location += f", {item.location.stream}"
                location += ")"
            console.print(f"  [bold]{item.rule_id}[/bold] {item.message}{location}")
            console.print(f"    Remediation: {item.remediation}", style="dim")
    incomplete = [result for result in report.results if result.reason]
    if incomplete:
        console.print("\n[bold]Incomplete rules[/bold]")
        for result in incomplete:
            console.print(f"  {result.rule_id}: {result.reason}", style="dim")
    if report.suppressed:
        console.print(f"\nSuppressed: {len(report.suppressed)} reviewed finding(s)")
    coverage = report.coverage
    if coverage is not None:
        bits = [f"{coverage.episodes} episodes"]
        if coverage.frames is not None:
            bits.append(f"{coverage.frames} frames")
        if coverage.tasks:
            bits.append(f"{len(coverage.tasks)} task label(s)")
        console.print("Coverage: " + ", ".join(bits), style="dim")
    if report.cache.hits:
        console.print(f"Cache: {report.cache.hits} hit(s)", style="dim")
    if report_path:
        console.print(f"\nReport: {report_path}")


def render_inventory(inventory: DatasetInventory, console: Console | None = None) -> None:
    console = console or Console()
    console.print(f"Dataset: [bold]{inventory.name}[/bold]")
    parts = [f"Adapter: {inventory.adapter} {inventory.format_version}"]
    if inventory.profile:
        parts.append(f"Profile: {inventory.profile}")
    if inventory.total_messages is not None:
        parts.append(f"Messages: {inventory.total_messages}")
    else:
        parts.extend([f"Episodes: {len(inventory.episodes)}", f"Frames: {inventory.total_frames}"])
    if inventory.fps is not None:
        parts.append(f"FPS: {inventory.fps:g}")
    console.print("  ".join(parts))
    table = Table("Stream", "Kind", "Dtype", "Shape")
    for stream in inventory.streams:
        table.add_row(stream.key, stream.kind, stream.dtype, str(stream.shape))
    console.print(table)


def render_rules(rules: list[RuleMetadata], console: Console | None = None) -> None:
    console = console or Console()
    table = Table("Rule ID", "Severity", "Cost", "Title")
    for metadata in rules:
        table.add_row(metadata.id, metadata.severity.value, metadata.cost, metadata.title)
    console.print(table)


def render_explanation(metadata: RuleMetadata, console: Console | None = None) -> None:
    console = console or Console()
    console.print(Text(metadata.id, style="bold"))
    console.print(f"{metadata.title} ({metadata.severity.value}, v{metadata.version})")
    console.print(f"\n{metadata.description}")
    console.print(f"\nRemediation: {metadata.remediation}")
    if metadata.limitations:
        console.print(f"\nLimitations: {metadata.limitations}")
    if metadata.option_defaults:
        console.print("\nOptions:")
        for key, value in metadata.option_defaults.items():
            console.print(f"  {key}: {value!r}")


def render_comparison(comparison: Comparison, report_path: Path | None = None, console: Console | None = None) -> None:
    console = console or Console()
    style = {"unchanged": "green", "improved": "green", "regressed": "bold red", "changed": "yellow"}[comparison.status]
    console.print(f"Baseline: [bold]{comparison.baseline_dataset}[/bold] ({comparison.baseline_status})")
    console.print(f"Candidate: [bold]{comparison.candidate_dataset}[/bold] ({comparison.candidate_status})")
    console.print(f"Result: [{style}]{comparison.status.upper()}[/{style}]")
    console.print(
        f"Findings: {len(comparison.new_findings)} new, "
        f"{len(comparison.resolved_findings)} resolved, "
        f"{len(comparison.persistent_findings)} persistent"
    )
    if comparison.new_findings:
        console.print("\n[bold red]New findings[/bold red]")
        for finding in comparison.new_findings:
            console.print(f"  [bold]{finding.rule_id}[/bold] {finding.message}")
    if comparison.resolved_findings:
        console.print("\n[green]Resolved findings[/green]")
        for finding in comparison.resolved_findings:
            console.print(f"  [bold]{finding.rule_id}[/bold] {finding.message}")
    if comparison.rule_changes:
        console.print("\n[bold]Rule status changes[/bold]")
        for change in comparison.rule_changes:
            console.print(f"  {change.rule_id}: {change.before} → {change.after}")
    delta = comparison.coverage
    if delta is not None:
        console.print("\n[bold]Coverage[/bold]")
        console.print(f"  Episodes: {delta.episodes_before} → {delta.episodes_after}")
        if delta.frames_before is not None or delta.frames_after is not None:
            console.print(f"  Frames: {delta.frames_before} → {delta.frames_after}")
        if delta.added_streams:
            console.print(f"  Added streams: {', '.join(delta.added_streams)}")
        if delta.removed_streams:
            console.print(f"  Removed streams: {', '.join(delta.removed_streams)}")
        if delta.added_tasks:
            console.print(f"  Added tasks: {', '.join(delta.added_tasks)}")
        if delta.removed_tasks:
            console.print(f"  Removed tasks: {', '.join(delta.removed_tasks)}")
        console.print("  Coverage lists what is present; it is not a quality score.", style="dim")
    if report_path:
        console.print(f"\nReport: {report_path}")
