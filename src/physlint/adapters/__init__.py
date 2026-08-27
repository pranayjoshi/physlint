"""Dataset adapter registry."""

from physlint.adapters.lerobot import LeRobotAdapter
from physlint.adapters.mcap import McapAdapter

__all__ = ["LeRobotAdapter", "McapAdapter"]
