"""Built-in rule registry."""

from physlint.models.rule import Rule
from physlint.rules.manifest import MANIFEST_RULES
from physlint.rules.mcap import MCAP_RULES, ROS2_RULES
from physlint.rules.numeric import NUMERIC_RULES
from physlint.rules.temporal import TEMPORAL_RULES
from physlint.rules.video import VIDEO_RULES

LEROBOT_RULES: list[Rule] = [*MANIFEST_RULES, *TEMPORAL_RULES, *NUMERIC_RULES, *VIDEO_RULES]
BUILTIN_RULES: list[Rule] = [*LEROBOT_RULES, *MCAP_RULES, *ROS2_RULES]


def rules_for(adapter: str, profile: str | None = None) -> list[Rule]:
    if adapter == "lerobot":
        return LEROBOT_RULES
    if adapter == "mcap":
        return [*MCAP_RULES, *(ROS2_RULES if profile == "ros2" else [])]
    return []


__all__ = ["BUILTIN_RULES", "rules_for"]
