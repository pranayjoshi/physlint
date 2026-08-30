"""Built-in rule registry."""

from collections.abc import Sequence

from physlint.models.rule import Rule
from physlint.rules.duplication import DUPLICATION_RULES
from physlint.rules.manifest import MANIFEST_RULES
from physlint.rules.mcap import MCAP_RULES, ROS2_RULES
from physlint.rules.numeric import NUMERIC_RULES
from physlint.rules.temporal import TEMPORAL_RULES
from physlint.rules.video import VIDEO_RULES

LEROBOT_RULES: list[Rule] = [*MANIFEST_RULES, *TEMPORAL_RULES, *NUMERIC_RULES, *VIDEO_RULES, *DUPLICATION_RULES]
BUILTIN_RULES: list[Rule] = [*LEROBOT_RULES, *MCAP_RULES, *ROS2_RULES]


def rules_for(adapter: str, profile: str | None = None, extra: Sequence[Rule] = ()) -> list[Rule]:
    if adapter == "lerobot":
        base: list[Rule] = list(LEROBOT_RULES)
    elif adapter == "mcap":
        base = [*MCAP_RULES, *(ROS2_RULES if profile == "ros2" else [])]
    else:
        base = []
    for rule in extra:
        adapters = rule.metadata.adapters
        if adapters and adapter not in adapters:
            continue
        base.append(rule)
    return base


__all__ = ["BUILTIN_RULES", "rules_for"]
