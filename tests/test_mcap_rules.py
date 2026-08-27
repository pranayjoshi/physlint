from __future__ import annotations

from physlint.config import Config, RuleSettings
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.models.finding import RuleStatus


def _result(report, rule_id: str):
    return next(item for item in report.results if item.rule_id == rule_id)


def test_clean_generic_mcap_passes(mcap_factory):
    report = run_validation(discover(mcap_factory()), Config())
    assert report.status == "passed"
    assert _result(report, "mcap.readable").status == RuleStatus.PASSED
    assert _result(report, "mcap.summary_consistency").status == RuleStatus.PASSED
    assert all(not result.rule_id.startswith("ros2.") for result in report.results)


def test_truncated_mcap_becomes_actionable_finding(mcap_factory):
    report = run_validation(discover(mcap_factory(truncate_bytes=24)), Config())
    result = _result(report, "mcap.readable")
    assert report.status == "failed"
    assert result.status == RuleStatus.FAILED
    assert "stopped" in result.findings[0].message


def test_timestamp_rollback_and_sequence_gap_are_detected(mcap_factory):
    path = mcap_factory(
        log_times_ns=[1_000_000_000, 900_000_000, 1_100_000_000],
        sequences=[1, 3, 4],
    )
    report = run_validation(discover(path), Config())
    assert report.status == "failed"
    assert _result(report, "mcap.timestamp_order").status == RuleStatus.FAILED
    assert _result(report, "mcap.sequence_continuity").status == RuleStatus.FAILED


def test_fastwrite_style_recording_reports_reduced_coverage_without_failing_contract(mcap_factory):
    report = run_validation(discover(mcap_factory(use_indexes=False)), Config())
    result = _result(report, "mcap.index_coverage")
    assert report.status == "passed"
    assert result.status == RuleStatus.FAILED
    assert result.findings[0].severity.value == "notice"


def test_clean_ros2_profile_decodes_and_checks_required_topics(ros2_mcap_factory):
    config = Config(
        rules={
            "ros2.required_topics": RuleSettings(options={"required_topics": ["/joint_states"]}),
            "ros2.header_clock_skew": RuleSettings(enabled=False),
        }
    )
    report = run_validation(discover(ros2_mcap_factory()), config)
    assert report.status == "passed"
    assert _result(report, "ros2.decode").status == RuleStatus.PASSED
    assert _result(report, "ros2.required_topics").status == RuleStatus.PASSED


def test_ros2_gap_and_joint_state_dimension_failures_are_detected(ros2_mcap_factory):
    config = Config(
        rules={
            "ros2.topic_gaps": RuleSettings(
                options={"topic_rates_hz": {"/joint_states": 10.0}, "max_gap_multiplier": 5.0}
            )
        }
    )
    report = run_validation(discover(ros2_mcap_factory(invalid_dimensions=True, gap=True)), config)
    assert report.status == "failed"
    assert _result(report, "ros2.topic_gaps").status == RuleStatus.FAILED
    assert _result(report, "ros2.semantic_consistency").status == RuleStatus.FAILED
