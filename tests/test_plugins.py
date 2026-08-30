from __future__ import annotations

from pathlib import Path

from physlint.config import Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import RuleStatus

PLUGIN = Path(__file__).resolve().parents[1] / "examples" / "plugins" / "idle_prefix.py"


def test_example_idle_prefix_plugin_detects_leading_hold(dataset_factory):
    actions = [[0.0, 0.0]] * 10 + [[1.0, 1.0]] * 6
    config = Config(plugins=[f"{PLUGIN}:IdlePrefixRule"])
    report = run_validation(discover(dataset_factory(actions=actions, episode_lengths=(10, 6))), config)
    result = next(item for item in report.results if item.rule_id == "example.idle_prefix")
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].observed["idle_samples"] >= 8
    assert "example.idle_prefix" in report.plugins


def test_example_idle_prefix_plugin_passes_moving_start(dataset_factory):
    config = Config(plugins=[f"{PLUGIN}:IdlePrefixRule"])
    report = run_validation(discover(dataset_factory()), config)
    result = next(item for item in report.results if item.rule_id == "example.idle_prefix")
    assert result.status == RuleStatus.PASSED
