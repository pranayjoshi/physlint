from __future__ import annotations

import json

from typer.testing import CliRunner

from physlint.cli import app

runner = CliRunner()


def test_init_json_creates_valid_config_and_preserves_existing_file(tmp_path):
    path = tmp_path / "contract.yaml"
    created = runner.invoke(app, ["init", "--path", str(path), "--format", "json"])
    assert created.exit_code == 0, created.output
    assert json.loads(created.stdout)["operation"] == "init"
    original = path.read_bytes()
    refused = runner.invoke(app, ["init", "--path", str(path), "--format", "json"])
    assert refused.exit_code == 2
    assert refused.stdout == ""
    assert json.loads(refused.stderr)["error_kind"] == "configuration"
    assert path.read_bytes() == original


def test_baseline_json_success_and_errors(dataset_factory, tmp_path):
    root = dataset_factory(timestamps=[0.0] * 12)
    destination = tmp_path / "baseline.yaml"
    args = [
        "baseline",
        str(root),
        "--author",
        "ada",
        "--reason",
        "reviewed",
        "--output",
        str(destination),
        "--format",
        "json",
    ]
    created = runner.invoke(app, args)
    assert created.exit_code == 0, created.output
    assert json.loads(created.stdout)["suppressions"] > 0
    refused = runner.invoke(app, args)
    assert refused.exit_code == 2
    assert json.loads(refused.stderr)["error_kind"] == "configuration"
    missing = runner.invoke(
        app,
        [
            "baseline",
            str(tmp_path / "missing"),
            "--author",
            "ada",
            "--reason",
            "reviewed",
            "--format",
            "json",
            "--output",
            str(tmp_path / "new.yaml"),
        ],
    )
    assert missing.exit_code == 3
    assert json.loads(missing.stderr)["error_kind"] == "source"
    assert not (tmp_path / "new.yaml").exists()


def test_doctor_reports_source_and_config_without_executing_plugins(dataset_factory, tmp_path):
    root = dataset_factory()
    marker = tmp_path / "executed"
    plugin = root / "plugin.py"
    plugin.write_text(f"from pathlib import Path\nPath({str(marker)!r}).touch()\n")
    (root / "physlint.yaml").write_text(f"plugins: ['{plugin}:Anything']\n")
    result = runner.invoke(app, ["doctor", str(root), "--format", "json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["status"] == "passed"
    assert any(item["name"] == "config_plugins" and item["status"] == "warning" for item in payload["checks"])
    assert not marker.exists()
    assert not (root / ".physlint").exists()


def test_doctor_missing_source_and_invalid_config_are_diagnostics(tmp_path):
    path = tmp_path / "invalid.yaml"
    path.write_text("unknown: true\n")
    result = runner.invoke(app, ["doctor", str(tmp_path / "missing"), "--config", str(path), "--format", "json"])
    assert result.exit_code == 2
    assert result.stderr == ""
    assert sum(item["status"] == "failed" for item in json.loads(result.stdout)["checks"]) == 2


def test_baseline_refuses_an_incomplete_validation(dataset_factory, tmp_path):
    root = dataset_factory()
    (root / "data/chunk-000/file-000.parquet").unlink()
    destination = tmp_path / "incomplete.yaml"
    result = runner.invoke(
        app,
        [
            "baseline",
            str(root),
            "--author",
            "ada",
            "--reason",
            "reviewed",
            "--output",
            str(destination),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 3, result.output
    assert json.loads(result.stderr)["error_kind"] == "source"
    assert not destination.exists()
