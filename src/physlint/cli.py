"""Physlint command-line interface and frozen exit codes."""

from __future__ import annotations

import json
from datetime import UTC
from enum import StrEnum
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from physlint import __version__
from physlint.adapters.base import AdapterError
from physlint.config import DEFAULT_CONFIG, ConfigurationError, load_config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.reporters.json import write_json_report
from physlint.reporters.terminal import (
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
    output: Annotated[
        OutputFormat, typer.Option("--output", "-o", help="Terminal or JSON stdout output.")
    ] = OutputFormat.TERMINAL,
    json_output: Annotated[Path | None, typer.Option("--json-output", help="Exact JSON report destination.")] = None,
) -> None:
    """Validate a dataset and return a CI-safe pass/fail exit code."""
    try:
        root = path.expanduser().resolve()
        settings = load_config(config.expanduser().resolve() if config else None, root)
        dataset = discover(root, settings.adapter, settings.profile)
        report = run_validation(dataset, settings)
        report_path: Path | None = None
        if json_output is not None:
            report_path = write_json_report(report, json_output)
        elif settings.reports.json_enabled:
            timestamp = report.started_at.astimezone(UTC).strftime("%Y-%m-%dT%H%M%SZ")
            report_path = write_json_report(report, Path(settings.reports.output_dir) / f"{timestamp}.json")
        if output == OutputFormat.JSON:
            typer.echo(report.model_dump_json(indent=2))
        else:
            render_report(report, report_path, console)
        adapter_errors = any(result.error_kind == "adapter" for result in report.results)
        rule_errors = any(result.error_kind == "rule" for result in report.results)
        if adapter_errors:
            raise typer.Exit(3)
        if rule_errors:
            raise typer.Exit(4)
        if report.status == "failed":
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
) -> None:
    """List built-in rules and their requirements."""
    metadata = [rule.metadata for rule in BUILTIN_RULES]
    if output_json:
        typer.echo(
            json.dumps(
                [
                    {
                        **item.__dict__,
                        "severity": item.severity.value,
                        "required_capabilities": sorted(item.required_capabilities),
                        "required_streams": sorted(item.required_streams),
                    }
                    for item in metadata
                ],
                indent=2,
            )
        )
    else:
        render_rules(metadata, console)


@app.command()
def explain(rule_id: Annotated[str, typer.Argument(help="Stable rule ID.")]) -> None:
    """Explain one rule, including remediation and limitations."""
    for rule in BUILTIN_RULES:
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
