from __future__ import annotations

import pytest

from physlint.config import Config, ConfigurationError, load_config
from physlint.engine.discovery import discover
from physlint.engine.planner import plan_rules


def test_rejects_unknown_top_level_key(tmp_path):
    path = tmp_path / "physlint.yaml"
    path.write_text("config_version: 1\nunknown: true\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="unknown"):
        load_config(path)


def test_rejects_unknown_rule_and_option(dataset_factory):
    dataset = discover(dataset_factory())
    with pytest.raises(ConfigurationError, match="unknown rule"):
        plan_rules(dataset, Config(rules={"made.up": {}}))
    with pytest.raises(ConfigurationError, match="unknown options"):
        plan_rules(
            dataset,
            Config(rules={"temporal.max_gap": {"options": {"made_up": 1}}}),
        )


def test_configuration_digest_is_stable():
    assert Config().digest() == Config().digest()


def test_rejects_invalid_option_values(dataset_factory):
    dataset = discover(dataset_factory())
    with pytest.raises(ConfigurationError, match="non-negative"):
        plan_rules(
            dataset,
            Config(rules={"temporal.max_gap": {"options": {"max_gap_ms": -1}}}),
        )
