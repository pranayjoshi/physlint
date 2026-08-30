from __future__ import annotations

import json
from pathlib import Path

from validation.build_observatory import DEFAULT_COMPARISONS, DEFAULT_OUTPUT, build


def test_observatory_catalog_is_generated_from_committed_reports(tmp_path: Path):
    generated = tmp_path / "observations.json"
    comparisons = tmp_path / "comparisons.json"
    build(generated, comparisons)
    assert generated.read_bytes() == DEFAULT_OUTPUT.read_bytes()
    assert comparisons.read_bytes() == DEFAULT_COMPARISONS.read_bytes()
    payload = json.loads(comparisons.read_text(encoding="utf-8"))
    assert payload["comparisons"]
    assert all(row["status"] == "regressed" for row in payload["comparisons"])
