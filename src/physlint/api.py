"""Stable library entry points independent of terminal behavior."""

from __future__ import annotations

from pathlib import Path

from physlint.config import Config, load_config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.dataset import DatasetInventory
from physlint.models.finding import Report


def inspect_dataset(path: str | Path, *, adapter: str = "auto") -> DatasetInventory:
    return discover(path, adapter).inventory


def check_dataset(
    path: str | Path,
    *,
    config: Config | None = None,
    config_path: str | Path | None = None,
) -> Report:
    root = Path(path).expanduser().resolve()
    resolved_config = config or load_config(
        Path(config_path).expanduser().resolve() if config_path is not None else None, root
    )
    dataset = discover(root, resolved_config.adapter)
    return run_validation(dataset, resolved_config)
