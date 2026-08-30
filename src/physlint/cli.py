"""Physlint command-line interface and frozen exit codes."""

from __future__ import annotations

import json
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from physlint import __version__
from physlint.adapters.base import AdapterError
from physlint.api import check_dataset, compare_sources, resolve_report
from physlint.config import DEFAULT_CONFIG, ConfigurationError, load_config
from physlint.engine.baseline import baseline_from_report, write_baseline
from physlint.engine.discovery import discover
from physlint.models.finding import Report
from physlint.models.rule import Rule
from physlint.plugins import load_plugin_rules
from physlint.reporters import write_configured_reports
from physlint.reporters.atomic import write_atomic_text
from physlint.reporters.terminal import (
    render_comparison,
    render_explanation,
    render_inventory,
    render_report,
    render_rules,
)
from physlint.rules import BUILTIN_RULES

app = typer.Typer(
    name="physlint",
    help="Find concrete integrity defects in physical-AI datasets and recordings.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)
console = Console()
error_console = Console(stderr=True)


class OutputFormat(StrEnum):
    TERMINAL = "terminal"
    JSON = "json"


class ProfileChoice(StrEnum):
    AUTO = "auto"
    GENERIC = "generic"
    ROS2 = "ros2"


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit(0)


@app.callback()
def main(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True, help="Show version."),
    ] = False,
) -> None:
    """Validate robot-learning data before it reaches training."""


@app.command()
def check(
    path: Annotated[Path, typer.Argument(help="Local LeRobot v3 dataset directory or MCAP recording.")],
    config: Annotated[Path | None, typer.Option("--config", "-c", help="Quality contract YAML file.")] = None,
    baseline: Annotated[Path | None, typer.Option("--baseline", help="Reviewed suppression baseline YAML.")] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", "-o", help="Terminal or JSON stdout output.")
    ] = OutputFormat.TERMINAL,
    json_output: Annotated[Path | None, typer.Option("--json-output", help="Exact JSON report destination.")] = None,
    junit_output: Annotated[Path | None, typer.Option("--junit-output", help="Exact JUnit XML destination.")] = None,
    sarif_output: Annotated[Path | None, typer.Option("--sarif-output", help="Exact SARIF destination.")] = None,
    html_output: Annotated[Path | None, typer.Option("--html-output", help="Exact HTML report destination.")] = None,
) -> None:
    """Validate a dataset and return a CI-safe pass/fail exit code."""
    try:
        root = path.expanduser().resolve()
        settings = load_config(config.expanduser().resolve() if config else None, root)
        report = check_dataset(root, config=settings, baseline_path=baseline)
        written = write_configured_reports(
            report,
            settings,
            json_output=json_output,
            junit_output=junit_output,
            sarif_output=sarif_output,
            html_output=html_output,
        )
        if output == OutputFormat.JSON:
            typer.echo(report.model_dump_json(indent=2))
        else:
            render_report(report, written[0] if written else None, console)
            for extra in written[1:]:
                console.print(f"Report: {extra}")
        _raise_for_report(report)
    except KeyboardInterrupt as exc:
        raise typer.Exit(130) from exc
    except ConfigurationError as exc:
        error_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    except AdapterError as exc:
        error_console.print(f"[red]Source error:[/red] {exc}")
        raise typer.Exit(3) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI must preserve the documented code
        error_console.print(f"[red]Internal Physlint error:[/red] {type(exc).__name__}: {exc}")
        raise typer.Exit(4) from exc


@app.command()
def inspect(
    path: Annotated[Path, typer.Argument(help="Local LeRobot v3 dataset directory or MCAP recording.")],
    output_json: Annotated[bool, typer.Option("--json", help="Print the inventory as JSON.")] = False,
    profile: Annotated[
        ProfileChoice,
        typer.Option("--profile", help="Auto-detect, use generic MCAP, or use ROS 2 semantics."),
    ] = ProfileChoice.AUTO,
) -> None:
    """Show streams, schemas, rates, and episode inventory."""
    try:
        inventory = discover(path, profile=profile.value).inventory
        if output_json:
            typer.echo(inventory.model_dump_json(indent=2))
        else:
            render_inventory(inventory, console)
    except AdapterError as exc:
        error_console.print(f"[red]Source error:[/red] {exc}")
        raise typer.Exit(3) from exc
    except KeyboardInterrupt as exc:
        raise typer.Exit(130) from exc


@app.command("rules")
def list_rules(
    output_json: Annotated[bool, typer.Option("--json", help="Print rule metadata as JSON.")] = False,
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Include plugins from a quality contract.")
    ] = None,
) -> None:
    """List built-in rules and their requirements."""
    try:
        rules = _rules_for_display(config)
    except ConfigurationError as exc:
        error_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    metadata = [rule.metadata for rule in rules]
    if output_json:
        typer.echo(
            json.dumps(
                [
                    {
                        **item.__dict__,
                        "severity": item.severity.value,
                        "required_capabilities": sorted(item.required_capabilities),
                        "required_streams": sorted(item.required_streams),
                        "adapters": sorted(item.adapters),
                    }
                    for item in metadata
                ],
                indent=2,
            )
        )
    else:
        render_rules(metadata, console)


@app.command()
def explain(
    rule_id: Annotated[str, typer.Argument(help="Stable rule ID.")],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Include plugins from a quality contract.")
    ] = None,
) -> None:
    """Explain one rule, including remediation and limitations."""
    try:
        rules = _rules_for_display(config)
    except ConfigurationError as exc:
        error_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    for rule in rules:
        if rule.metadata.id == rule_id:
            render_explanation(rule.metadata, console)
            return
    error_console.print(f"[red]Unknown rule ID:[/red] {rule_id}")
    raise typer.Exit(2)


@app.command()
def init(
    path: Annotated[Path, typer.Option("--path", "-p", help="Configuration file to create.")] = Path("physlint.yaml"),
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
) -> None:
    """Generate a documented quality-contract configuration."""
    destination = path.expanduser().resolve()
    if destination.exists() and not force:
        error_console.print(f"[red]Refusing to overwrite existing file:[/red] {destination}")
        raise typer.Exit(2)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(DEFAULT_CONFIG, encoding="utf-8")
    console.print(f"Created {destination}")


@app.command()
def compare(
    baseline: Annotated[Path, typer.Argument(help="Baseline dataset, recording, or JSON report.")],
    candidate: Annotated[Path, typer.Argument(help="Candidate dataset, recording, or JSON report.")],
    config: Annotated[Path | None, typer.Option("--config", "-c", help="Quality contract YAML file.")] = None,
    output: Annotated[
        OutputFormat, typer.Option("--output", "-o", help="Terminal or JSON stdout output.")
    ] = OutputFormat.TERMINAL,
    json_output: Annotated[
        Path | None, typer.Option("--json-output", help="Exact JSON comparison destination.")
    ] = None,
) -> None:
    """Compare two dataset versions and report regressions without a quality score."""
    try:
        settings = load_config(config.expanduser().resolve() if config else None)
        comparison = compare_sources(baseline, candidate, config=settings)
        report_path: Path | None = None
        if json_output is not None:
            report_path = write_atomic_text(json_output, comparison.model_dump_json(indent=2) + "\n")
        if output == OutputFormat.JSON:
            typer.echo(comparison.model_dump_json(indent=2))
        else:
            render_comparison(comparison, report_path, console)
        if comparison.status == "regressed":
            raise typer.Exit(1)
    except KeyboardInterrupt as exc:
        raise typer.Exit(130) from exc
    except ConfigurationError as exc:
        error_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    except AdapterError as exc:
        error_console.print(f"[red]Source error:[/red] {exc}")
        raise typer.Exit(3) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI must preserve the documented code
        error_console.print(f"[red]Internal Physlint error:[/red] {type(exc).__name__}: {exc}")
        raise typer.Exit(4) from exc


@app.command()
def baseline(
    path: Annotated[Path, typer.Argument(help="Dataset, recording, or JSON report to snapshot.")],
    author: Annotated[str, typer.Option("--author", help="Person accepting the current findings.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these fingerprints are accepted.")],
    output_path: Annotated[Path, typer.Option("--output", "-o", help="Baseline YAML destination.")] = Path(
        ".physlint/baseline.yaml"
    ),
    expires: Annotated[str | None, typer.Option("--expires", help="Optional expiry date YYYY-MM-DD.")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c", help="Quality contract YAML file.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing baseline.")] = False,
) -> None:
    """Create a reviewed exception baseline from current findings."""
    try:
        destination = output_path.expanduser().resolve()
        if destination.exists() and not force:
            error_console.print(f"[red]Refusing to overwrite existing file:[/red] {destination}")
            raise typer.Exit(2)
        settings = load_config(config.expanduser().resolve() if config else None, path)
        report = resolve_report(path, config=settings)
        expires_at = date.fromisoformat(expires) if expires else None
        document = baseline_from_report(report, author=author, reason=reason, expires_at=expires_at)
        write_baseline(document, destination)
        console.print(f"Wrote {len(document.suppressions)} suppression(s) to {destination}")
    except KeyboardInterrupt as exc:
        raise typer.Exit(130) from exc
    except (ConfigurationError, ValueError) as exc:
        error_console.print(f"[red]Configuration error:[/red] {exc}")
        raise typer.Exit(2) from exc
    except AdapterError as exc:
        error_console.print(f"[red]Source error:[/red] {exc}")
        raise typer.Exit(3) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI must preserve the documented code
        error_console.print(f"[red]Internal Physlint error:[/red] {type(exc).__name__}: {exc}")
        raise typer.Exit(4) from exc


def _rules_for_display(config_path: Path | None) -> list[Rule]:
    settings = load_config(config_path.expanduser().resolve() if config_path else None)
    return [*BUILTIN_RULES, *load_plugin_rules(settings.plugins)]


def _raise_for_report(report: Report) -> None:
    adapter_errors = any(result.error_kind == "adapter" for result in report.results)
    rule_errors = any(result.error_kind == "rule" for result in report.results)
    if adapter_errors:
        raise typer.Exit(3)
    if rule_errors:
        raise typer.Exit(4)
    if report.status == "failed":
        raise typer.Exit(1)
