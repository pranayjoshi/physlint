"""Disk cache for expensive rule results keyed by source fingerprint."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from physlint.config import CacheSettings
from physlint.engine.planner import PlannedRule
from physlint.models.finding import RuleResult
from physlint.reporters.atomic import write_atomic_text

CACHE_SCHEMA = "1"
CACHED_COSTS = frozenset({"video"})


class RuleCache:
    def __init__(self, settings: CacheSettings, *, source_fingerprint: str, dataset_path: str, physlint_version: str):
        self.enabled = settings.enabled
        self.directory = Path(settings.directory).expanduser().resolve() if settings.enabled else None
        self.source_fingerprint = source_fingerprint
        self.dataset_path = dataset_path
        self.physlint_version = physlint_version
        self.hits = 0
        self.misses = 0

    def get(self, planned: PlannedRule) -> RuleResult | None:
        if not self._cacheable(planned) or self.directory is None:
            return None
        path = self._path(planned)
        if not path.is_file():
            self.misses += 1
            return None
        try:
            result = RuleResult.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError):
            self.misses += 1
            return None
        if result.rule_id != planned.rule.metadata.id or result.status.value == "errored":
            self.misses += 1
            return None
        self.hits += 1
        return result.model_copy(update={"cached": True})

    def put(self, planned: PlannedRule, result: RuleResult) -> None:
        if not self._cacheable(planned) or self.directory is None or result.status.value == "errored":
            return
        write_atomic_text(self._path(planned), result.model_dump_json(indent=2) + "\n")

    def _cacheable(self, planned: PlannedRule) -> bool:
        return self.enabled and planned.rule.metadata.cost in CACHED_COSTS and planned.not_run_reason is None

    def _path(self, planned: PlannedRule) -> Path:
        assert self.directory is not None
        return self.directory / f"{self._key(planned)}.json"

    def _key(self, planned: PlannedRule) -> str:
        payload: dict[str, Any] = {
            "schema": CACHE_SCHEMA,
            "physlint_version": self.physlint_version,
            "dataset_path": self.dataset_path,
            "source_fingerprint": self.source_fingerprint,
            "rule_id": planned.rule.metadata.id,
            "rule_version": planned.rule.metadata.version,
            "severity": planned.severity.value,
            "options": planned.options,
        }
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
        return hashlib.sha256(encoded.encode()).hexdigest()
