"""Regenerate the committed machine-contract JSON Schemas."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from physlint.config import Config
from physlint.models.cli import CliError, DemoResult
from physlint.models.comparison import Comparison
from physlint.models.dataset import DatasetInventory
from physlint.models.finding import Report

SCHEMAS: dict[str, type[BaseModel]] = {
    "report-1.0.json": Report,
    "config-1.json": Config,
    "inventory-1.0.json": DatasetInventory,
    "comparison-1.0.json": Comparison,
    "error-1.0.json": CliError,
    "demo-1.0.json": DemoResult,
}


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "schemas"
    destination.mkdir(exist_ok=True)
    for filename, model in SCHEMAS.items():
        payload = json.dumps(model.model_json_schema(by_alias=True), indent=2) + "\n"
        (destination / filename).write_text(payload, encoding="utf-8")


if __name__ == "__main__":
    main()
