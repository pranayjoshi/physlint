"""Concise Rich terminal presentation."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.text import Text

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
