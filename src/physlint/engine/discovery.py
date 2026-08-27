"""Format-aware local source discovery."""

from __future__ import annotations

import json
from pathlib import Path

from physlint.adapters.base import AdapterError, UnsupportedDatasetError
from physlint.adapters.lerobot import LeRobotAdapter
from physlint.adapters.mcap import McapAdapter, has_mcap_magic
from physlint.models.dataset import DatasetView


def discover(path: str | Path, adapter: str = "auto", profile: str = "auto") -> DatasetView:
    source = Path(path).expanduser().resolve()
    if not source.exists():
        raise AdapterError(f"source path does not exist: {source}")
    if adapter not in {"auto", "lerobot", "mcap"}:
        raise UnsupportedDatasetError(f"unknown adapter: {adapter}")
    if profile not in {"auto", "generic", "ros2"}:
        raise UnsupportedDatasetError(f"unknown profile: {profile}")
    if adapter == "lerobot" or (adapter == "auto" and source.is_dir() and is_lerobot(source)):
        if not source.is_dir():
            raise AdapterError(f"LeRobot source must be a directory: {source}")
        return LeRobotAdapter(source)
    mcap_path = resolve_mcap_source(source)
    if adapter == "mcap" or (adapter == "auto" and mcap_path is not None):
        if mcap_path is None:
            raise AdapterError(f"no MCAP recording found at {source}")
        return McapAdapter(mcap_path, profile)
    if source.suffix.lower() == ".db3" or (source.is_dir() and list(source.glob("*.db3"))):
        raise UnsupportedDatasetError(
            "ROS 2 SQLite .db3 bags are not supported in this alpha; convert with "
            "`ros2 bag convert` to MCAP and rerun Physlint"
        )
    raise UnsupportedDatasetError(f"no adapter recognizes {source}; expected a LeRobot v3 directory or MCAP recording")


def resolve_mcap_source(source: Path) -> Path | None:
    if source.is_file() and (source.suffix.lower() == ".mcap" or has_mcap_magic(source)):
        return source
    if not source.is_dir():
        return None
    candidates = sorted(source.glob("*.mcap"))
    if len(candidates) == 1:
        return candidates[0]
    if len(candidates) > 1:
        raise AdapterError(f"multiple MCAP files found in {source}; pass one recording path explicitly")
    return None


def is_lerobot(root: Path) -> bool:
    info_path = root / "meta" / "info.json"
    if not info_path.is_file():
        return False
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(info, dict) and "features" in info and "fps" in info
