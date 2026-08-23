"""Physlint public package."""

from physlint._version import __version__ as __version__
from physlint.api import check_dataset, inspect_dataset

__all__ = ["check_dataset", "inspect_dataset"]
