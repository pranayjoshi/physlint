from __future__ import annotations

from pathlib import Path

import pytest

from validation.prepare_demo import _replace_link


def test_prepare_demo_replaces_symlink_but_not_directory(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    _replace_link(link, target, force=False)
    assert link.is_symlink()
    with pytest.raises(FileExistsError):
        _replace_link(link, target, force=False)
    _replace_link(link, target, force=True)

    directory = tmp_path / "directory"
    directory.mkdir()
    with pytest.raises(IsADirectoryError):
        _replace_link(directory, target, force=True)
