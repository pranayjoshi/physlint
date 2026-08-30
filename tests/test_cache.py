from __future__ import annotations

from physlint.config import CacheSettings, Config
from physlint.engine.cache import CACHED_COSTS, RuleCache
from physlint.engine.discovery import discover
from physlint.engine.planner import plan_rules
from physlint.engine.runner import run_validation, source_fingerprint
from physlint.models.finding import RuleStatus


def test_video_rule_results_are_cached_across_runs(dataset_factory, tmp_path):
    root = dataset_factory(include_video=True)
    config = Config(cache=CacheSettings(enabled=True, directory=str(tmp_path / "cache")))
    first = run_validation(discover(root), config)
    second = run_validation(discover(root), config)
    cached = [result for result in second.results if result.rule_id.startswith("video.") and result.cached]
    assert first.cache.misses >= 1
    assert second.cache.hits >= 1
    assert cached
    assert {result.status for result in cached} == {RuleStatus.PASSED}


def test_cache_key_includes_source_fingerprint(dataset_factory, tmp_path):
    root = dataset_factory(include_video=True)
    dataset = discover(root)
    planned = next(
        item
        for item in plan_rules(dataset, Config())
        if item.rule.metadata.cost in CACHED_COSTS and not item.not_run_reason
    )
    cache = RuleCache(
        CacheSettings(enabled=True, directory=str(tmp_path / "cache")),
        source_fingerprint=source_fingerprint(root),
        dataset_path=str(root),
        physlint_version="test",
    )
    assert cache.get(planned) is None
