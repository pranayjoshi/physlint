"""Read-only runtime, optional dependency, configuration, and source diagnostics."""

from __future__ import annotations

import platform
import sys
from importlib import import_module, metadata
from pathlib import Path

from physlint._version import __version__
from physlint.adapters.base import AdapterError
from physlint.config import ConfigurationError, load_config, resolve_config_path
from physlint.engine.discovery import discover
from physlint.models.cli import DiagnosticCheck, DoctorResult
from physlint.sources import resolve_source


def diagnose(
    source: str | None = None,
    *,
    config_path: Path | None = None,
    offline: bool = False,
) -> DoctorResult:
    checks = [
        DiagnosticCheck(
            name="python",
            status="passed" if sys.version_info >= (3, 11) else "failed",
            detail=f"Python {platform.python_version()} on {platform.system()}",
            remediation=None if sys.version_info >= (3, 11) else "Install Python 3.11 or newer.",
        )
    ]
    for distribution, module, extra in (
        ("numpy", "numpy", None),
        ("pyarrow", "pyarrow", None),
        ("mcap", "mcap", None),
        ("mcap-ros2-support", "mcap_ros2", None),
        ("opencv-python-headless", "cv2", "video"),
        ("huggingface-hub", "huggingface_hub", "hub"),
    ):
        try:
            imported = import_module(module)
            try:
                version = metadata.version(distribution)
            except metadata.PackageNotFoundError:
                version = str(getattr(imported, "__version__", "available"))
            checks.append(DiagnosticCheck(name=module, status="passed", detail=version))
        except (ImportError, OSError, RuntimeError) as exc:
            install = f"physlint[{extra}]" if extra else "physlint"
            checks.append(
                DiagnosticCheck(
                    name=module,
                    status="warning" if extra else "failed",
                    detail=str(exc),
                    remediation=f'Install a compatible dependency: python -m pip install "{install}"',
                )
            )
    root: Path | None = None
    if source:
        try:
            resolved = resolve_source(source, offline=offline)
            root = resolved.path
            view = discover(root)
            inventory = view.inventory
            checks.append(
                DiagnosticCheck(
                    name="source",
                    status="passed",
                    detail=f"{inventory.adapter} {inventory.format_version}: {len(inventory.episodes)} episodes",
                )
            )
        except AdapterError as exc:
            checks.append(
                DiagnosticCheck(
                    name="source",
                    status="failed",
                    detail=str(exc),
                    remediation="Check the source path, supported format, and cached Hub revision.",
                )
            )
    try:
        path = resolve_config_path(config_path.expanduser().resolve() if config_path else None, root or Path.cwd())
        settings = load_config(path)
        checks.append(DiagnosticCheck(name="configuration", status="passed", detail=str(path) if path else "Defaults"))
        if settings.plugins:
            checks.append(
                DiagnosticCheck(
                    name="config_plugins",
                    status="warning",
                    detail=f"{len(settings.plugins)} configured plugin(s) ignored",
                    remediation="Enable configuration plugins only after reviewing their code.",
                )
            )
    except ConfigurationError as exc:
        checks.append(
            DiagnosticCheck(
                name="configuration", status="failed", detail=str(exc), remediation="Fix the quality contract YAML."
            )
        )
    return DoctorResult(
        physlint_version=__version__,
        status="failed" if any(item.status == "failed" for item in checks) else "passed",
        checks=checks,
    )
