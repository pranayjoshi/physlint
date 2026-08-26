"""Create safe, short demo paths for recording terminal screenshots."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

from validation.harness import parse_download_path

REPO_ID = "ViaCatalyst/robomimic-can-ph-lerobot-v3"
REVISION = "71bfefc1ff8ef8735840bb761d41f4fc3a527f20"


def downloaded_clean_root() -> Path:
    completed = subprocess.run(  # noqa: S603
        [
            "hf",
            "download",
            REPO_ID,
            "--repo-type",
            "dataset",
            "--revision",
            REVISION,
            "--format",
            "quiet",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return parse_download_path(completed.stdout)


def _replace_link(path: Path, target: Path, force: bool) -> None:
    if path.exists() or path.is_symlink():
        if not force:
            raise FileExistsError(f"demo path already exists; remove it or pass --force: {path}")
        if not path.is_symlink():
            raise IsADirectoryError(f"refusing to replace a non-symlink demo path: {path}")
        path.unlink()
    path.symlink_to(target, target_is_directory=True)


def prepare(output: Path, corruption: Path, force: bool = False) -> tuple[Path, Path]:
    if not corruption.is_dir():
        raise FileNotFoundError(f"missing corruption copy; run python -m validation.harness first: {corruption}")
    output.mkdir(parents=True, exist_ok=True)
    clean = downloaded_clean_root()
    clean_link = output / "clean"
    nan_link = output / "nan"
    _replace_link(clean_link, clean, force)
    _replace_link(nan_link, corruption.resolve(), force)
    return clean_link, nan_link


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--output", type=Path, default=Path("/tmp/physlint-demo"))
    result.add_argument("--corruption", type=Path, default=Path("validation/.work/corruption-nan"))
    result.add_argument(
        "--force",
        action="store_true",
        help="Replace existing symlinks only; never delete directories.",
    )
    return result


if __name__ == "__main__":
    clean_path, nan_path = prepare(**vars(parser().parse_args()))
    print(f"clean={clean_path}")
    print(f"nan={nan_path}")
