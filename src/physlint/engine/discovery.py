"""Metadata-only dataset discovery."""

from __future__ import annotations

import json
from pathlib import Path

from physlint.adapters.base import AdapterError, UnsupportedDatasetError
from physlint.adapters.lerobot import LeRobotAdapter


def discover(path: str | Path, adapter: str = "auto") -> LeRobotAdapter:
    root = Path(path).expanduser().resolve()
    if not root.exists():
        raise AdapterError(f"dataset path does not exist: {root}")
    if not root.is_dir():
        raise AdapterError(f"dataset path is not a directory: {root}")
    if adapter not in {"auto", "lerobot"}:
        raise UnsupportedDatasetError(f"unknown adapter: {adapter}")
    if adapter == "lerobot" or is_lerobot(root):
        return LeRobotAdapter(root)
    raise UnsupportedDatasetError(f"no adapter recognizes {root}; expected a LeRobot v3 meta/info.json")


def is_lerobot(root: Path) -> bool:
    info_path = root / "meta" / "info.json"
    if not info_path.is_file():
        return False
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(info, dict) and "features" in info and "fps" in info
