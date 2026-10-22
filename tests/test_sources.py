from __future__ import annotations

import sys
from types import ModuleType

import pytest

from physlint.adapters.base import AdapterError
from physlint.api import check_dataset
from physlint.sources import parse_hugging_face_source, resolve_source


def test_hugging_face_source_requires_revision():
    with pytest.raises(AdapterError, match="must include a revision"):
        parse_hugging_face_source("hf://datasets/example/robot-data")


def test_hugging_face_source_resolves_snapshot_and_preserves_identity(dataset_factory, tmp_path, monkeypatch):
    snapshot = (
        tmp_path / "hub" / "datasets--example--robot-data" / "snapshots" / "0123456789abcdef0123456789abcdef01234567"
    )
    snapshot.parent.mkdir(parents=True)
    dataset_factory(repo_id=None).rename(snapshot)
    calls: list[dict[str, object]] = []
    module = ModuleType("huggingface_hub")

    def snapshot_download(**kwargs):
        calls.append(kwargs)
        return str(snapshot)

    module.snapshot_download = snapshot_download  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "huggingface_hub", module)
    source = "hf://datasets/example/robot-data@main"

    resolved = resolve_source(source, offline=True, cache_dir=tmp_path / "cache")
    report = check_dataset(source, offline=True, cache_dir=tmp_path / "cache")

    assert resolved.path == snapshot
    assert resolved.revision == "0123456789abcdef0123456789abcdef01234567"
    assert report.dataset_path == ("hf://datasets/example/robot-data@0123456789abcdef0123456789abcdef01234567")
    assert report.source_revision == "0123456789abcdef0123456789abcdef01234567"
    assert calls[0]["local_files_only"] is True
