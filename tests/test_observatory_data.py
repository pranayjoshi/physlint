from __future__ import annotations

from pathlib import Path

from validation.build_observatory import DEFAULT_OUTPUT, build


def test_observatory_catalog_is_generated_from_committed_reports(tmp_path: Path):
    generated = tmp_path / "observations.json"
    build(generated)
    assert generated.read_bytes() == DEFAULT_OUTPUT.read_bytes()
