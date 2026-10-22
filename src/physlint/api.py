"""Stable library entry points independent of terminal behavior."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from physlint.config import Config, ConfigurationError, load_config, resolve_config_path
from physlint.engine.baseline import apply_baseline, load_baseline
from physlint.engine.compare import compare_reports
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.comparison import Comparison
from physlint.models.dataset import DatasetInventory
from physlint.models.finding import Report, Severity
from physlint.sources import resolve_source


def inspect_dataset(
    path: str | Path,
    *,
    adapter: str = "auto",
    profile: str = "auto",
    offline: bool = False,
    cache_dir: str | Path | None = None,
) -> DatasetInventory:
    source = resolve_source(path, offline=offline, cache_dir=cache_dir)
    inventory = discover(source.path, adapter, profile).inventory
    return inventory.model_copy(
        update={
            "path": source.display_path,
            "source_revision": source.revision or inventory.source_revision,
        }
    )


def check_dataset(
    path: str | Path,
    *,
    config: Config | None = None,
    config_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
    offline: bool = False,
    cache_dir: str | Path | None = None,
    allow_config_plugins: bool = False,
) -> Report:
    source = resolve_source(path, offline=offline, cache_dir=cache_dir)
    root = source.path
    requested_config_path = Path(config_path).expanduser().resolve() if config_path is not None else None
    resolved_config_path = resolve_config_path(requested_config_path, root) if config is None else requested_config_path
    resolved_config = config or load_config(resolved_config_path, root)
    if baseline_path is not None:
        resolved_config = resolved_config.model_copy(update={"baseline": str(Path(baseline_path).expanduser())})
    dataset = discover(root, resolved_config.adapter, resolved_config.profile)
    report = run_validation(
        dataset,
        resolved_config,
        allow_config_plugins=allow_config_plugins,
        configuration_path=str(resolved_config_path) if resolved_config_path is not None else None,
        reported_dataset_path=source.display_path,
    )
    if source.revision is not None:
        report = report.model_copy(update={"source_revision": source.revision})
    return _apply_configured_baseline(report, resolved_config)


def load_report(path: str | Path) -> Report:
    source = Path(path).expanduser().resolve()
    try:
        return Report.model_validate_json(source.read_text(encoding="utf-8"))
    except (OSError, ValidationError, ValueError) as exc:
        raise ConfigurationError(f"invalid Physlint report {source}: {exc}") from exc


def resolve_report(
    path: str | Path,
    *,
    config: Config | None = None,
    config_path: str | Path | None = None,
    offline: bool = False,
    cache_dir: str | Path | None = None,
    allow_config_plugins: bool = False,
) -> Report:
    if not str(path).startswith("hf://"):
        source = Path(path).expanduser().resolve()
        if source.is_file() and source.suffix.lower() == ".json":
            return load_report(source)
    return check_dataset(
        path,
        config=config,
        config_path=config_path,
        offline=offline,
        cache_dir=cache_dir,
        allow_config_plugins=allow_config_plugins,
    )


def compare_sources(
    baseline: str | Path,
    candidate: str | Path,
    *,
    config: Config | None = None,
    config_path: str | Path | None = None,
    offline: bool = False,
    cache_dir: str | Path | None = None,
    allow_config_plugins: bool = False,
) -> Comparison:
    resolved = config or load_config(Path(config_path).expanduser().resolve() if config_path is not None else None)
    left = resolve_report(
        baseline,
        config=resolved,
        offline=offline,
        cache_dir=cache_dir,
        allow_config_plugins=allow_config_plugins,
    )
    right = resolve_report(
        candidate,
        config=resolved,
        offline=offline,
        cache_dir=cache_dir,
        allow_config_plugins=allow_config_plugins,
    )
    return compare_reports(left, right, fail_on=Severity(resolved.fail_on))


def _apply_configured_baseline(report: Report, config: Config) -> Report:
    if not config.baseline:
        return report
    return apply_baseline(
        report,
        load_baseline(Path(config.baseline).expanduser().resolve()),
        fail_on=Severity(config.fail_on),
    )
