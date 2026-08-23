"""Built-in rule registry."""

from physlint.models.rule import Rule
from physlint.rules.manifest import MANIFEST_RULES
from physlint.rules.numeric import NUMERIC_RULES
from physlint.rules.temporal import TEMPORAL_RULES
from physlint.rules.video import VIDEO_RULES

BUILTIN_RULES: list[Rule] = [*MANIFEST_RULES, *TEMPORAL_RULES, *NUMERIC_RULES, *VIDEO_RULES]

__all__ = ["BUILTIN_RULES"]
