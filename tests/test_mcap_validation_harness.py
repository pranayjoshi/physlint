from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from validation.mcap_harness import (
    DEFAULT_MANIFEST,
    load_manifest,
    parse_recording_overrides,
    run,
    sha256_file,
)


def test_mcap_manifest_is_pinned():
    manifest = load_manifest(DEFAULT_MANIFEST)
    assert len(manifest["public_recordings"]) >= 2
    for public in manifest["public_recordings"]:
        assert len(public["source_revision"]) == 40
        assert len(public["sha256"]) == 64
        assert public["source_revision"] in public["source_url"]


def test_mcap_harness_runs_offline_with_verified_public_fixture(tmp_path: Path, mcap_factory):
    manifest = load_manifest(DEFAULT_MANIFEST)
    public = manifest["public_recordings"][0]
    source = mcap_factory()
    public["sha256"] = sha256_file(source)
    public["expected_status"] = "passed"
    public["expected_failed_rules"] = []
    manifest["public_recordings"] = [public]
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest), encoding="utf-8")

    output = tmp_path / "reports"
    run(
        argparse.Namespace(
            manifest=manifest_path,
            output=output,
            work=tmp_path / "work",
            recording=[f"{public['id']}={source}"],
        )
    )
    summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
    assert summary["expected_outcomes_verified"] == 3
    assert {row["profile"] for row in summary["results"]} == {"generic", "ros2"}


def test_recording_overrides_are_keyed_by_manifest_id(tmp_path: Path):
    first = tmp_path / "one.mcap"
    second = tmp_path / "two.mcap"

    result = parse_recording_overrides([f"one={first}", f"two={second}"])

    assert result == {"one": first.resolve(), "two": second.resolve()}
