from __future__ import annotations

import json

from typer.testing import CliRunner

from physlint.cli import app

runner = CliRunner()


def test_core_cli_workflow(dataset_factory, tmp_path):
    root = dataset_factory()
    report_path = tmp_path / "report.json"
    check = runner.invoke(
        app,
        ["check", str(root), "--output", "json", "--json-output", str(report_path)],
    )
    assert check.exit_code == 0, check.output
    assert json.loads(check.stdout)["status"] == "passed"
    assert report_path.is_file()

    inspect = runner.invoke(app, ["inspect", str(root), "--json"])
    assert inspect.exit_code == 0
    assert json.loads(inspect.stdout)["total_frames"] == 12

    rules = runner.invoke(app, ["rules", "--json"])
    assert rules.exit_code == 0
    assert len(json.loads(rules.stdout)) == 31

    explain = runner.invoke(app, ["explain", "temporal.max_gap"])
    assert explain.exit_code == 0
    assert "max_gap_ms" in explain.stdout


def test_cli_contract_failure_returns_one(dataset_factory, tmp_path):
    timestamps = [0, 0, 2 / 30, 3 / 30, 4 / 30, 5 / 30] * 2
    result = runner.invoke(
        app,
        [
            "check",
            str(dataset_factory(timestamps=timestamps)),
            "--json-output",
            str(tmp_path / "failed.json"),
        ],
    )
    assert result.exit_code == 1
    assert "FAIL" in result.stdout


def test_cli_configuration_and_dataset_exit_codes(dataset_factory, tmp_path):
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("unknown: true\n", encoding="utf-8")
    config_result = runner.invoke(app, ["check", str(dataset_factory()), "--config", str(invalid)])
    assert config_result.exit_code == 2
    assert "Configuration error" in config_result.output

    dataset_result = runner.invoke(app, ["check", str(tmp_path / "missing")])
    assert dataset_result.exit_code == 3
    assert "Source error" in dataset_result.output


def test_init_refuses_overwrite(tmp_path):
    destination = tmp_path / "physlint.yaml"
    first = runner.invoke(app, ["init", "--path", str(destination)])
    assert first.exit_code == 0
    second = runner.invoke(app, ["init", "--path", str(destination)])
    assert second.exit_code == 2
    assert "Refusing to overwrite" in second.output


def test_version_command():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.stdout.strip() == "0.2.0a1"


def test_cli_checks_and_inspects_mcap(mcap_factory, tmp_path):
    source = mcap_factory()
    report_path = tmp_path / "mcap-report.json"
    check = runner.invoke(
        app,
        ["check", str(source), "--output", "json", "--json-output", str(report_path)],
    )
    assert check.exit_code == 0, check.output
    report = json.loads(check.stdout)
    assert report["adapter"] == "mcap"
    assert report["source_fingerprint_method"] == "file-content-sha256-v1"
    assert report_path.is_file()

    inspect = runner.invoke(app, ["inspect", str(source), "--json"])
    assert inspect.exit_code == 0, inspect.output
    inventory = json.loads(inspect.stdout)
    assert inventory["profile"] == "generic"
    assert inventory["total_messages"] == 3


def test_cli_force_ros2_profile(ros2_mcap_factory):
    source = ros2_mcap_factory()
    result = runner.invoke(app, ["inspect", str(source), "--profile", "ros2", "--json"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["profile"] == "ros2"


def test_generated_cross_format_config_does_not_block_mcap(mcap_factory, tmp_path):
    config = tmp_path / "physlint.yaml"
    assert runner.invoke(app, ["init", "--path", str(config)]).exit_code == 0
    result = runner.invoke(app, ["check", str(mcap_factory()), "--config", str(config)])
    assert result.exit_code == 0, result.output
