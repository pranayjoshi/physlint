from __future__ import annotations

import argparse
import json
from pathlib import Path

import pytest
import yaml

from physlint import __version__
from validation.survey_harness import load_survey_manifest, run


def test_survey_manifest_is_pinned_and_versioned():
    root = Path(__file__).resolve().parents[1]
    manifest = load_survey_manifest(root / "validation" / "survey_manifest.yaml")
    assert manifest["physlint_version"] == __version__
    assert manifest["tier"] == "compatibility-survey"
    assert len(manifest["datasets"]) >= 10
    assert len(manifest["screens"]) >= 5
    cells = {cell for record in manifest["datasets"] for cell in record["cells"]}
    assert "producer-official" in cells
    assert "embodiment-bimanual" in cells
    assert "embodiment-mobile" in cells
    for record in manifest["datasets"]:
        assert len(record["revision"]) == 40
        assert record["repo_id"] != "lerobot/svla_so101_pickplace"


def test_survey_manifest_rejects_release_gate_shape(tmp_path: Path):
    path = tmp_path / "survey.yaml"
    path.write_text("schema_version: 1\ndatasets: []\n", encoding="utf-8")
    with pytest.raises(ValueError, match="compatibility-survey"):
        load_survey_manifest(path)


def test_survey_harness_records_failures_and_rejects_v2(dataset_factory, tmp_path: Path):
    clean = dataset_factory()
    v2 = tmp_path / "v2"
    (v2 / "meta").mkdir(parents=True)
    (v2 / "meta" / "info.json").write_text(
        json.dumps({"codebase_version": "v2.1", "fps": 30, "features": {"action": {"dtype": "float32", "shape": [2]}}}),
        encoding="utf-8",
    )
    manifest = {
        "schema_version": 1,
        "run_id": "survey-fixture",
        "physlint_version": __version__,
        "tier": "compatibility-survey",
        "claim": "fixture",
        "datasets": [
            {
                "id": "fixture-clean",
                "title": "Fixture",
                "repo_id": "tests/fixture",
                "revision": "0" * 40,
                "robot": "testbot",
                "fps": 30,
                "cells": ["test"],
            }
        ],
        "screens": [
            {
                "id": "fixture-v21",
                "title": "v2.1 fixture",
                "repo_id": "tests/v2",
                "revision": "1" * 40,
                "expected_error": "unsupported LeRobot version v2.1",
                "reason": "fail closed",
                "cells": ["version-v2.1"],
            }
        ],
        "deferred": [],
        "skipped": [],
    }
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")
    output = tmp_path / "reports"
    run(
        argparse.Namespace(
            manifest=manifest_path,
            output=output,
            work=tmp_path / "work",
            dataset_root=[f"fixture-clean={clean}", f"fixture-v21={v2}"],
            only=[],
        )
    )
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["tier"] == "compatibility-survey"
    assert summary["checked_passed"] == 1
    assert summary["screens_rejected"] == 1
    assert (output / "check-fixture-clean.json").is_file()

    run(
        argparse.Namespace(
            manifest=manifest_path,
            output=output,
            work=tmp_path / "work",
            dataset_root=[f"fixture-clean={clean}", f"fixture-v21={v2}"],
            only=["fixture-v21"],
        )
    )
    rerun = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert rerun["checked_passed"] == 1
    assert rerun["screens_rejected"] == 1
