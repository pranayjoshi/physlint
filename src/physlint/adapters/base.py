"""Adapter errors shared by discovery and the CLI."""


class AdapterError(RuntimeError):
    """The selected adapter could not safely read the dataset."""


class UnsupportedDatasetError(AdapterError):
    """No installed adapter recognizes the source."""
