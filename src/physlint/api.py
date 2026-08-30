"""Stable library entry points independent of terminal behavior."""

from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from physlint.config import Config, ConfigurationError, load_config
from physlint.engine.baseline import apply_baseline, load_baseline
from physlint.engine.compare import compare_reports
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.comparison import Comparison
from physlint.models.dataset import DatasetInventory
from physlint.models.finding import Report, Severity


def inspect_dataset(path: str | Path, *, adapter: str = "auto", profile: str = "auto") -> DatasetInventory:
    return discover(path, adapter, profile).inventory


def check_dataset(
    path: str | Path,
    *,
    config: Config | None = None,
    config_path: str | Path | None = None,
    baseline_path: str | Path | None = None,
) -> Report:
    root = Path(path).expanduser().resolve()
    resolved_config = config or load_config(
        Path(config_path).expanduser().resolve() if config_path is not None else None, root
    )
    if baseline_path is not None:
        resolved_config = resolved_config.model_copy(update={"baseline": str(Path(baseline_path).expanduser())})
    dataset = discover(root, resolved_config.adapter, resolved_config.profile)
    report = run_validation(dataset, resolved_config)
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
) -> Report:
    source = Path(path).expanduser().resolve()
    if source.is_file() and source.suffix.lower() == ".json":
        return load_report(source)
    return check_dataset(source, config=config, config_path=config_path)


def compare_sources(
    baseline: str | Path,
    candidate: str | Path,
    *,
    config: Config | None = None,
    config_path: str | Path | None = None,
) -> Comparison:
    resolved = config or load_config(Path(config_path).expanduser().resolve() if config_path is not None else None)
    left = resolve_report(baseline, config=resolved)
    right = resolve_report(candidate, config=resolved)
    return compare_reports(left, right, fail_on=Severity(resolved.fail_on))


def _apply_configured_baseline(report: Report, config: Config) -> Report:
    if not config.baseline:
        return report
    return apply_baseline(
        report,
        load_baseline(Path(config.baseline).expanduser().resolve()),
        fail_on=Severity(config.fail_on),
    )
