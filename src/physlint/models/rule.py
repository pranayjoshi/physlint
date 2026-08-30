"""Rule metadata and execution contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from physlint.models.dataset import DatasetView
from physlint.models.finding import Finding, Severity


@dataclass(frozen=True)
class RuleMetadata:
    id: str
    version: str
    title: str
    description: str
    severity: Severity
    scope: str
    cost: str
    required_capabilities: frozenset[str] = frozenset()
    required_streams: frozenset[str] = frozenset()
    option_defaults: dict[str, Any] = field(default_factory=dict)
    adapters: frozenset[str] = field(default_factory=frozenset)
    limitations: str = ""
    remediation: str = "Inspect and recollect affected source data."


class Rule(Protocol):
    metadata: RuleMetadata

    def run(self, dataset: DatasetView, options: dict[str, Any], severity: Severity) -> list[Finding]: ...


class RuleNotApplicable(RuntimeError):
    """The adapter can run a rule in principle, but this dataset lacks its contract input."""
