"""Physlint command-line interface and frozen exit codes."""

from __future__ import annotations

import json
import tempfile
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

import typer
from pydantic import BaseModel
from rich.console import Console

from physlint import __version__
from physlint.adapters.base import AdapterError
from physlint.api import check_dataset, compare_sources, inspect_dataset, resolve_report
from physlint.config import DEFAULT_CONFIG, CacheSettings, Config, ConfigurationError, load_config
from physlint.demo import write_demo_dataset
from physlint.doctor import diagnose
from physlint.engine.baseline import baseline_from_report, write_baseline
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.cli import CliError, DemoResult, DoctorResult, WriteResult
from physlint.models.comparison import Comparison
from physlint.models.dataset import DatasetInventory
from physlint.models.finding import Report
from physlint.models.rule import Rule, RuleMetadata
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


class SchemaChoice(StrEnum):
    REPORT = "report"
    CONFIG = "config"
    INVENTORY = "inventory"
    COMPARISON = "comparison"
    ERROR = "error"
    DEMO = "demo"
    DOCTOR = "doctor"
    WRITE = "write"


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
    source: Annotated[
        str,
        typer.Argument(help="Local LeRobot v3/MCAP path or hf://datasets/OWNER/NAME@REVISION."),
    ],
    config: Annotated[Path | None, typer.Option("--config", "-c", help="Quality contract YAML file.")] = None,
    baseline: Annotated[Path | None, typer.Option("--baseline", help="Reviewed suppression baseline YAML.")] = None,
    output: Annotated[
        OutputFormat,
        typer.Option("--format", "--output", "-f", "-o", help="Terminal or JSON stdout output."),
    ] = OutputFormat.TERMINAL,
    json_output: Annotated[Path | None, typer.Option("--json-output", help="Exact JSON report destination.")] = None,
    junit_output: Annotated[Path | None, typer.Option("--junit-output", help="Exact JUnit XML destination.")] = None,
    sarif_output: Annotated[Path | None, typer.Option("--sarif-output", help="Exact SARIF destination.")] = None,
    html_output: Annotated[Path | None, typer.Option("--html-output", help="Exact HTML report destination.")] = None,
    offline: Annotated[
        bool, typer.Option("--offline", help="Use only files already present in the Hub cache.")
    ] = False,
    hub_cache: Annotated[Path | None, typer.Option("--hub-cache", help="Hugging Face cache directory.")] = None,
    safe: Annotated[
        bool,
        typer.Option(
            "--safe/--allow-config-plugins",
            help="Ignore executable plugins named by physlint.yaml (safe by default).",
        ),
    ] = True,
) -> None:
    """Validate a dataset and return a CI-safe pass/fail exit code."""
    try:
        report = check_dataset(
            source,
            config_path=config,
            baseline_path=baseline,
            offline=offline,
            cache_dir=hub_cache,
            allow_config_plugins=not safe,
        )
        settings = load_config(Path(report.configuration_path)) if report.configuration_path else Config()
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
        _raise_for_report(report, output)
    except KeyboardInterrupt as exc:
        _render_error("interrupted", "validation interrupted", 130, output)
        raise typer.Exit(130) from exc
    except ConfigurationError as exc:
        _render_error("configuration", str(exc), 2, output)
        raise typer.Exit(2) from exc
    except AdapterError as exc:
        _render_error("source", str(exc), 3, output)
        raise typer.Exit(3) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI must preserve the documented code
        _render_error("internal", f"{type(exc).__name__}: {exc}", 4, output)
        raise typer.Exit(4) from exc


@app.command()
def inspect(
    source: Annotated[
        str,
        typer.Argument(help="Local LeRobot v3/MCAP path or hf://datasets/OWNER/NAME@REVISION."),
    ],
    output: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Terminal or JSON stdout output.")
    ] = OutputFormat.TERMINAL,
    output_json: Annotated[bool, typer.Option("--json", help="Alias for --format json.")] = False,
    profile: Annotated[
        ProfileChoice,
        typer.Option("--profile", help="Auto-detect, use generic MCAP, or use ROS 2 semantics."),
    ] = ProfileChoice.AUTO,
    offline: Annotated[
        bool, typer.Option("--offline", help="Use only files already present in the Hub cache.")
    ] = False,
    hub_cache: Annotated[Path | None, typer.Option("--hub-cache", help="Hugging Face cache directory.")] = None,
) -> None:
    """Show streams, schemas, rates, and episode inventory."""
    try:
        inventory = inspect_dataset(
            source,
            profile=profile.value,
            offline=offline,
            cache_dir=hub_cache,
        )
        if output_json or output == OutputFormat.JSON:
            typer.echo(inventory.model_dump_json(indent=2))
        else:
            render_inventory(inventory, console)
    except AdapterError as exc:
        _render_error("source", str(exc), 3, OutputFormat.JSON if output_json else output)
        raise typer.Exit(3) from exc
    except KeyboardInterrupt as exc:
        _render_error("interrupted", "inspection interrupted", 130, OutputFormat.JSON if output_json else output)
        raise typer.Exit(130) from exc
    except Exception as exc:  # noqa: BLE001 - CLI must preserve the documented code
        _render_error(
            "internal",
            f"{type(exc).__name__}: {exc}",
            4,
            OutputFormat.JSON if output_json else output,
        )
        raise typer.Exit(4) from exc


@app.command("rules")
def list_rules(
    output: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Terminal or JSON stdout output.")
    ] = OutputFormat.TERMINAL,
    output_json: Annotated[bool, typer.Option("--json", help="Alias for --format json.")] = False,
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Include plugins from a quality contract.")
    ] = None,
    safe: Annotated[
        bool,
        typer.Option("--safe/--allow-config-plugins", help="Ignore config-declared plugins (safe by default)."),
    ] = True,
) -> None:
    """List built-in rules and their requirements."""
    try:
        rules = _rules_for_display(config, allow_config_plugins=not safe)
    except ConfigurationError as exc:
        _render_error("configuration", str(exc), 2, OutputFormat.JSON if output_json else output)
        raise typer.Exit(2) from exc
    metadata = [rule.metadata for rule in rules]
    if output_json or output == OutputFormat.JSON:
        typer.echo(json.dumps([_rule_metadata_json(item) for item in metadata], indent=2))
    else:
        render_rules(metadata, console)


@app.command()
def explain(
    rule_id: Annotated[str, typer.Argument(help="Stable rule ID.")],
    config: Annotated[
        Path | None, typer.Option("--config", "-c", help="Include plugins from a quality contract.")
    ] = None,
    output: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Terminal or JSON stdout output.")
    ] = OutputFormat.TERMINAL,
    safe: Annotated[
        bool,
        typer.Option("--safe/--allow-config-plugins", help="Ignore config-declared plugins (safe by default)."),
    ] = True,
) -> None:
    """Explain one rule, including remediation and limitations."""
    try:
        rules = _rules_for_display(config, allow_config_plugins=not safe)
    except ConfigurationError as exc:
        _render_error("configuration", str(exc), 2, output)
        raise typer.Exit(2) from exc
    for rule in rules:
        if rule.metadata.id == rule_id:
            if output == OutputFormat.JSON:
                typer.echo(json.dumps(_rule_metadata_json(rule.metadata), indent=2))
            else:
                render_explanation(rule.metadata, console)
            return
    _render_error("configuration", f"unknown rule ID: {rule_id}", 2, output)
    raise typer.Exit(2)


@app.command("schema")
def show_schema(
    name: Annotated[SchemaChoice, typer.Argument(help="Machine contract to describe.")],
) -> None:
    """Print a versioned JSON Schema for a machine-readable Physlint document."""
    models: dict[SchemaChoice, type[BaseModel]] = {
        SchemaChoice.REPORT: Report,
        SchemaChoice.CONFIG: Config,
        SchemaChoice.INVENTORY: DatasetInventory,
        SchemaChoice.COMPARISON: Comparison,
        SchemaChoice.ERROR: CliError,
        SchemaChoice.DEMO: DemoResult,
        SchemaChoice.DOCTOR: DoctorResult,
        SchemaChoice.WRITE: WriteResult,
    }
    typer.echo(json.dumps(models[name].model_json_schema(by_alias=True), indent=2))


@app.command()
def demo(
    output: Annotated[
        OutputFormat, typer.Option("--format", "-f", help="Terminal or JSON stdout output.")
    ] = OutputFormat.TERMINAL,
) -> None:
    """Run one healthy and one intentionally corrupted dataset in a few seconds."""
    try:
        with tempfile.TemporaryDirectory(prefix="physlint-demo-") as temporary:
            root = Path(temporary)
            clean_dataset = discover(write_demo_dataset(root / "clean", corrupted=False))
            corrupt_dataset = discover(write_demo_dataset(root / "corrupted", corrupted=True))
            settings = Config(cache=CacheSettings(enabled=False))
            clean = run_validation(
                clean_dataset,
                settings,
                extra_rules=[],
                allow_config_plugins=False,
                reported_dataset_path="demo://clean",
            )
            corrupted = run_validation(
                corrupt_dataset,
                settings,
                extra_rules=[],
                allow_config_plugins=False,
                reported_dataset_path="demo://corrupted",
            )
            succeeded = clean.status == "passed" and corrupted.status == "failed"
            result = DemoResult(
                status="passed" if succeeded else "failed",
                clean=clean,
                corrupted=corrupted,
            )
            if output == OutputFormat.JSON:
                typer.echo(result.model_dump_json(indent=2))
            else:
                console.print("[bold]Healthy demo dataset[/bold]")
                render_report(clean, console=console)
                console.print("\n[bold]Dataset with one injected NaN[/bold]")
                render_report(corrupted, console=console)
                if succeeded:
                    console.print("\n[green]Demo passed:[/green] Physlint accepted healthy data and caught the defect.")
            if not succeeded:
                raise typer.Exit(4)
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - demo preserves the CLI error contract
        _render_error("internal", f"{type(exc).__name__}: {exc}", 4, output)
        raise typer.Exit(4) from exc


@app.command()
def init(
    path: Annotated[Path, typer.Option("--path", "-p", help="Configuration file to create.")] = Path("physlint.yaml"),
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing file.")] = False,
    output: Annotated[OutputFormat, typer.Option("--format", "-f")] = OutputFormat.TERMINAL,
) -> None:
    """Generate a documented quality-contract configuration."""
    try:
        destination = path.expanduser().resolve()
        if destination.exists() and not force:
            raise ConfigurationError(f"Refusing to overwrite existing file: {destination}")
        write_atomic_text(destination, DEFAULT_CONFIG)
        if output == OutputFormat.JSON:
            typer.echo(WriteResult(operation="init", path=str(destination)).model_dump_json(indent=2))
        else:
            console.print(f"Created {destination}")
    except KeyboardInterrupt as exc:
        _render_error("interrupted", "configuration creation interrupted", 130, output)
        raise typer.Exit(130) from exc
    except (ConfigurationError, OSError) as exc:
        _render_error("configuration", str(exc), 2, output)
        raise typer.Exit(2) from exc


@app.command()
def doctor(
    source: Annotated[str | None, typer.Argument(help="Optional source to inspect without running rules.")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c")] = None,
    offline: Annotated[bool, typer.Option("--offline")] = False,
    output: Annotated[OutputFormat, typer.Option("--format", "-f")] = OutputFormat.TERMINAL,
) -> None:
    """Diagnose runtime, optional dependencies, source layout, and configuration."""
    try:
        result = diagnose(source, config_path=config, offline=offline)
        if output == OutputFormat.JSON:
            typer.echo(result.model_dump_json(indent=2))
        else:
            for item in result.checks:
                console.print(f"{item.status.upper()}: {item.name}: {item.detail}")
                if item.remediation:
                    console.print(f"  {item.remediation}")
        if result.status == "failed":
            raise typer.Exit(2)
    except typer.Exit:
        raise
    except KeyboardInterrupt as exc:
        _render_error("interrupted", "diagnostics interrupted", 130, output)
        raise typer.Exit(130) from exc
    except Exception as exc:
        _render_error("internal", f"{type(exc).__name__}: {exc}", 4, output)
        raise typer.Exit(4) from exc


@app.command()
def compare(
    baseline: Annotated[str, typer.Argument(help="Baseline dataset, recording, Hub source, or JSON report.")],
    candidate: Annotated[str, typer.Argument(help="Candidate dataset, recording, Hub source, or JSON report.")],
    config: Annotated[Path | None, typer.Option("--config", "-c", help="Quality contract YAML file.")] = None,
    output: Annotated[
        OutputFormat,
        typer.Option("--format", "--output", "-f", "-o", help="Terminal or JSON stdout output."),
    ] = OutputFormat.TERMINAL,
    json_output: Annotated[
        Path | None, typer.Option("--json-output", help="Exact JSON comparison destination.")
    ] = None,
    offline: Annotated[
        bool, typer.Option("--offline", help="Use only files already present in the Hub cache.")
    ] = False,
    hub_cache: Annotated[Path | None, typer.Option("--hub-cache", help="Hugging Face cache directory.")] = None,
    safe: Annotated[
        bool,
        typer.Option("--safe/--allow-config-plugins", help="Ignore config-declared plugins (safe by default)."),
    ] = True,
) -> None:
    """Compare two dataset versions and report regressions without a quality score."""
    try:
        settings = load_config(config.expanduser().resolve() if config else None)
        comparison = compare_sources(
            baseline,
            candidate,
            config=settings,
            offline=offline,
            cache_dir=hub_cache,
            allow_config_plugins=not safe,
        )
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
        _render_error("interrupted", "comparison interrupted", 130, output)
        raise typer.Exit(130) from exc
    except ConfigurationError as exc:
        _render_error("configuration", str(exc), 2, output)
        raise typer.Exit(2) from exc
    except AdapterError as exc:
        _render_error("source", str(exc), 3, output)
        raise typer.Exit(3) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI must preserve the documented code
        _render_error("internal", f"{type(exc).__name__}: {exc}", 4, output)
        raise typer.Exit(4) from exc


@app.command()
def baseline(
    source: Annotated[
        str,
        typer.Argument(help="Dataset, recording, Hub source, or JSON report to snapshot."),
    ],
    author: Annotated[str, typer.Option("--author", help="Person accepting the current findings.")],
    reason: Annotated[str, typer.Option("--reason", help="Why these fingerprints are accepted.")],
    output_path: Annotated[Path, typer.Option("--output", "-o", help="Baseline YAML destination.")] = Path(
        ".physlint/baseline.yaml"
    ),
    expires: Annotated[str | None, typer.Option("--expires", help="Optional expiry date YYYY-MM-DD.")] = None,
    config: Annotated[Path | None, typer.Option("--config", "-c", help="Quality contract YAML file.")] = None,
    force: Annotated[bool, typer.Option("--force", help="Overwrite an existing baseline.")] = False,
    output: Annotated[OutputFormat, typer.Option("--format", "-f")] = OutputFormat.TERMINAL,
    offline: Annotated[
        bool, typer.Option("--offline", help="Use only files already present in the Hub cache.")
    ] = False,
    hub_cache: Annotated[Path | None, typer.Option("--hub-cache", help="Hugging Face cache directory.")] = None,
    safe: Annotated[
        bool,
        typer.Option("--safe/--allow-config-plugins", help="Ignore config-declared plugins (safe by default)."),
    ] = True,
) -> None:
    """Create a reviewed exception baseline from current findings."""
    try:
        destination = output_path.expanduser().resolve()
        if destination.exists() and not force:
            raise ConfigurationError(f"Refusing to overwrite existing file: {destination}")
        report = resolve_report(
            source,
            config_path=config,
            offline=offline,
            cache_dir=hub_cache,
            allow_config_plugins=not safe,
        )
        _raise_for_report_errors(report)
        expires_at = date.fromisoformat(expires) if expires else None
        document = baseline_from_report(report, author=author, reason=reason, expires_at=expires_at)
        write_baseline(document, destination)
        if output == OutputFormat.JSON:
            typer.echo(
                WriteResult(
                    operation="baseline", path=str(destination), suppressions=len(document.suppressions)
                ).model_dump_json(indent=2)
            )
        else:
            console.print(f"Wrote {len(document.suppressions)} suppression(s) to {destination}")
    except KeyboardInterrupt as exc:
        _render_error("interrupted", "baseline creation interrupted", 130, output)
        raise typer.Exit(130) from exc
    except (ConfigurationError, ValueError) as exc:
        _render_error("configuration", str(exc), 2, output)
        raise typer.Exit(2) from exc
    except AdapterError as exc:
        _render_error("source", str(exc), 3, output)
        raise typer.Exit(3) from exc
    except typer.Exit:
        raise
    except Exception as exc:  # noqa: BLE001 - CLI must preserve the documented code
        _render_error("internal", f"{type(exc).__name__}: {exc}", 4, output)
        raise typer.Exit(4) from exc


def _raise_for_report_errors(report: Report) -> None:
    for result in report.results:
        if result.error_kind == "adapter":
            raise AdapterError(result.reason or "Source validation could not complete")
        if result.error_kind == "rule":
            raise RuntimeError(result.reason or "Rule validation could not complete")


def _rules_for_display(config_path: Path | None, *, allow_config_plugins: bool = False) -> list[Rule]:
    settings = load_config(config_path.expanduser().resolve() if config_path else None)
    return [*BUILTIN_RULES, *load_plugin_rules(settings.plugins if allow_config_plugins else [])]


def _rule_metadata_json(metadata: RuleMetadata) -> dict[str, object]:
    return {
        **metadata.__dict__,
        "severity": metadata.severity.value,
        "required_capabilities": sorted(metadata.required_capabilities),
        "required_streams": sorted(metadata.required_streams),
        "adapters": sorted(metadata.adapters),
    }


def _render_error(
    kind: Literal["configuration", "source", "internal", "interrupted"],
    message: str,
    exit_code: int,
    output: OutputFormat,
) -> None:
    if output == OutputFormat.JSON:
        typer.echo(
            CliError(error_kind=kind, message=message, exit_code=exit_code).model_dump_json(indent=2),
            err=True,
        )
        return
    label = {
        "configuration": "Configuration error",
        "source": "Source error",
        "internal": "Internal Physlint error",
        "interrupted": "Interrupted",
    }[kind]
    error_console.print(f"[red]{label}:[/red] {message}")


def _raise_for_report(report: Report, output: OutputFormat = OutputFormat.TERMINAL) -> None:
    adapter_errors = any(result.error_kind == "adapter" for result in report.results)
    rule_errors = any(result.error_kind == "rule" for result in report.results)
    if adapter_errors:
        reason = next(
            (result.reason for result in report.results if result.error_kind == "adapter" and result.reason),
            "validation stopped because the source adapter failed",
        )
        _render_error("source", reason, 3, output)
        raise typer.Exit(3)
    if rule_errors:
        reason = next(
            (result.reason for result in report.results if result.error_kind == "rule" and result.reason),
            "validation stopped because a rule failed internally",
        )
        _render_error("internal", reason, 4, output)
        raise typer.Exit(4)
    if report.status == "failed":
        raise typer.Exit(1)
