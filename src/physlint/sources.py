"""Resolve local paths and explicit Hugging Face dataset references."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from typing import Any, cast

from physlint.adapters.base import AdapterError

HF_PREFIX = "hf://datasets/"
_REPO_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/[A-Za-z0-9][A-Za-z0-9._-]*$")


@dataclass(frozen=True)
class ResolvedSource:
    """A local validation path plus its reproducible public identity."""

    path: Path
    display_path: str
    revision: str | None = None
    remote: bool = False


def is_hugging_face_source(value: str | Path) -> bool:
    return str(value).startswith(HF_PREFIX)


def resolve_source(
    value: str | Path,
    *,
    offline: bool = False,
    cache_dir: str | Path | None = None,
) -> ResolvedSource:
    raw = str(value)
    if not is_hugging_face_source(raw):
        path = Path(value).expanduser().resolve()
        return ResolvedSource(path=path, display_path=str(path))

    repo_id, requested_revision = parse_hugging_face_source(raw)
    try:
        hub = import_module("huggingface_hub")
        snapshot_download = cast(Callable[..., Any], hub.snapshot_download)
    except (ImportError, AttributeError) as exc:
        raise AdapterError("Hugging Face sources require the optional dependency; install `physlint[hub]`") from exc

    kwargs: dict[str, object] = {
        "repo_id": repo_id,
        "repo_type": "dataset",
        "revision": requested_revision,
        "local_files_only": offline,
    }
    if cache_dir is not None:
        kwargs["cache_dir"] = str(Path(cache_dir).expanduser().resolve())
    try:
        snapshot = Path(snapshot_download(**kwargs)).resolve()
    except Exception as exc:  # noqa: BLE001 - normalize optional client failures
        mode = "offline cache" if offline else "Hugging Face Hub"
        raise AdapterError(f"cannot resolve {raw} from the {mode}: {exc}") from exc

    revision = _snapshot_revision(snapshot)
    if revision is None:
        raise AdapterError("Hub download did not return an immutable snapshot commit; cannot record source provenance")
    display_path = f"{HF_PREFIX}{repo_id}@{revision}"
    return ResolvedSource(path=snapshot, display_path=display_path, revision=revision, remote=True)


def parse_hugging_face_source(value: str) -> tuple[str, str]:
    if not value.startswith(HF_PREFIX):
        raise AdapterError(f"invalid Hugging Face dataset source: {value}")
    identity = value.removeprefix(HF_PREFIX)
    repo_id, separator, revision = identity.rpartition("@")
    if not separator or not repo_id or not revision:
        raise AdapterError("Hugging Face sources must include a revision: hf://datasets/owner/dataset@commit-or-tag")
    if not _REPO_ID.fullmatch(repo_id):
        raise AdapterError(f"invalid Hugging Face dataset ID: {repo_id!r}")
    if any(character.isspace() for character in revision):
        raise AdapterError("Hugging Face revision must not contain whitespace")
    return repo_id, revision


def _snapshot_revision(path: Path) -> str | None:
    if path.parent.name == "snapshots" and re.fullmatch(r"[0-9a-fA-F]{40}", path.name):
        return path.name
    return None
