"""Load third-party rules from config specs or installed entry points."""

from __future__ import annotations

import importlib
import importlib.util
import sys
from importlib.metadata import entry_points
from pathlib import Path
from types import ModuleType

from physlint.config import ConfigurationError
from physlint.models.rule import Rule, RuleMetadata

ENTRY_POINT_GROUP = "physlint.rules"


def load_plugin_rules(specs: list[str] | None = None) -> list[Rule]:
    rules: list[Rule] = []
    seen: set[str] = set()
    for spec in _entry_point_specs():
        _register(rules, seen, load_rule(spec), spec)
    for spec in specs or []:
        _register(rules, seen, load_rule(spec), spec)
    return rules


def load_rule(spec: str) -> Rule:
    module_name, separator, attribute = spec.partition(":")
    if not separator or not module_name.strip() or not attribute.strip():
        raise ConfigurationError(f"plugin spec must be module:Class or path.py:Class, got {spec!r}")
    module = _load_module(module_name.strip())
    try:
        target = getattr(module, attribute.strip())
    except AttributeError as exc:
        raise ConfigurationError(f"plugin {spec!r} does not define {attribute.strip()}") from exc
    rule = target() if isinstance(target, type) else target
    _validate_rule(rule, spec)
    return rule  # type: ignore[no-any-return]


def _entry_point_specs() -> list[str]:
    try:
        discovered = entry_points(group=ENTRY_POINT_GROUP)
    except TypeError:  # pragma: no cover - importlib API variance
        discovered = entry_points().select(group=ENTRY_POINT_GROUP)
    return [item.value for item in discovered]


def _load_module(name: str) -> ModuleType:
    path = Path(name).expanduser()
    if path.suffix == ".py":
        resolved = path.resolve()
        if not resolved.is_file():
            raise ConfigurationError(f"plugin file does not exist: {resolved}")
        spec = importlib.util.spec_from_file_location(f"physlint_plugin_{resolved.stem}", resolved)
        if spec is None or spec.loader is None:
            raise ConfigurationError(f"cannot import plugin file: {resolved}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module
    try:
        return importlib.import_module(name)
    except ImportError as exc:
        raise ConfigurationError(f"cannot import plugin module {name!r}: {exc}") from exc


def _validate_rule(rule: object, spec: str) -> None:
    metadata = getattr(rule, "metadata", None)
    run = getattr(rule, "run", None)
    if not isinstance(metadata, RuleMetadata) or not callable(run):
        raise ConfigurationError(f"plugin {spec!r} is not a Physlint rule")
    if not metadata.id.strip():
        raise ConfigurationError(f"plugin {spec!r} is missing a rule ID")


def _register(rules: list[Rule], seen: set[str], rule: Rule, spec: str) -> None:
    rule_id = rule.metadata.id
    if rule_id in seen:
        raise ConfigurationError(f"duplicate plugin rule ID {rule_id} from {spec}")
    seen.add(rule_id)
    rules.append(rule)
