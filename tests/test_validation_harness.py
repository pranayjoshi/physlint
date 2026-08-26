from __future__ import annotations

import json
from pathlib import Path

import pytest

from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import RuleStatus
from validation.harness import (
    copy_and_corrupt,
    load_manifest,
    parse_download_path,
    parse_root_overrides,
    sanitized_report,
)
from validation.render_assets import render


def test_real_data_corruption_recipe_is_copy_only_and_detected(dataset_factory, tmp_path: Path):
    source = dataset_factory()
    destination = tmp_path / "corrupted"
    recipe = {
        "mutation": "insert_nan",
        "stream": "observation.state",
        "sample": 5,
        "dimension": 0,
    }
    copy_and_corrupt(source, destination, recipe)

    clean = run_validation(discover(source), Config())
    corrupted = run_validation(discover(destination), Config())
    finite = next(result for result in corrupted.results if result.rule_id == "numeric.finite_values")
    overlap = next(result for result in corrupted.results if result.rule_id == "temporal.stream_overlap")
    assert clean.status == "passed"
    assert finite.status == RuleStatus.FAILED
    assert overlap.status == RuleStatus.PASSED


def test_report_sanitizer_replaces_identity_and_local_path(dataset_factory):
    report = run_validation(discover(dataset_factory()), Config())
    safe = sanitized_report(report, "example/data", "abc123", "hf://datasets/example/data@abc123")
    assert safe.dataset == "example/data"
    assert safe.source_revision == "abc123"
    assert safe.dataset_path == "hf://datasets/example/data@abc123"
    assert "/private/" not in safe.model_dump_json()


def test_root_override_validation(tmp_path: Path):
    assert parse_root_overrides([f"sample={tmp_path}"]) == {"sample": tmp_path.resolve()}
    with pytest.raises(ValueError, match="ID=PATH"):
        parse_root_overrides(["invalid"])


def test_hf_download_path_parser_accepts_bare_and_human_output(tmp_path: Path):
    human = f"✓ Downloaded\n  path: {tmp_path}\n"
    assert parse_download_path(human) == tmp_path.resolve()
    assert parse_download_path(f"path={tmp_path}\n") == tmp_path.resolve()
    assert parse_download_path(f"{tmp_path}\n") == tmp_path.resolve()
    with pytest.raises(RuntimeError, match="did not return"):
        parse_download_path("✓ Downloaded\n")


def test_manifest_rejects_unsafe_work_directory_ids(tmp_path: Path):
    manifest = tmp_path / "manifest.yaml"
    manifest.write_text(
        "schema_version: 1\ndatasets:\n  - id: ../../outside\ncorruptions: []\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="IDs"):
        load_manifest(manifest)


def test_launch_card_is_rendered_from_summary(tmp_path: Path):
    summary = tmp_path / "summary.json"
    summary.write_text(
        json.dumps(
            {
                "clean_passed": 4,
                "clean_datasets": 4,
                "controlled_corruptions_detected": 3,
                "controlled_corruptions": 3,
                "episodes": 74,
                "frames": 31_258,
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "card.svg"
    render(summary, output)
    payload = output.read_text(encoding="utf-8")
    assert "31,258" in payload
    assert "4/4" in payload
    assert "<title>" in payload
