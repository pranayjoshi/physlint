from __future__ import annotations

import tomllib
from pathlib import Path

import yaml

from physlint import __version__
from validation.harness import load_manifest
from validation.mcap_harness import load_manifest as load_mcap_manifest
from validation.survey_harness import load_survey_manifest


def test_package_and_validation_versions_are_synchronized():
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    manifest = load_manifest(root / "validation" / "manifest.yaml")
    mcap_manifest = load_mcap_manifest(root / "validation" / "mcap_manifest.yaml")
    survey_manifest = load_survey_manifest(root / "validation" / "survey_manifest.yaml")
    assert project["project"]["version"] == __version__
    assert manifest["physlint_version"] == __version__
    assert mcap_manifest["physlint_version"] == __version__
    assert survey_manifest["physlint_version"] == __version__


def test_github_action_is_safe_by_default():
    root = Path(__file__).resolve().parents[1]
    action = yaml.safe_load((root / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    assert action["inputs"]["allow-config-plugins"]["default"] == "false"
    assert action["inputs"]["offline"]["default"] == "false"
