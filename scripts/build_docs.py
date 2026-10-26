"""Build the public documentation using maintained repository Markdown.

uv run --extra docs python scripts/build_docs.py
Only navigation pages are published; internal launch notes stay in the repo.
"""

from __future__ import annotations

import argparse
import re
import shutil
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from mkdocs.commands.build import build
from mkdocs.config import load_config

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/pranayjoshi/physlint/blob/master/"
PAGES = (
    "index.md",
    "cli.md",
    "configuration.md",
    "adapters/lerobot.md",
    "adapters/mcap-ros2.md",
    "rules/mvp-rules.md",
    "rules/mcap-ros2-rules.md",
    "agents.md",
    "python-api.md",
    "plugins.md",
    "release-0.4.0.md",
    "roadmap.md",
)


def rewrite_link(match: re.Match[str], source: Path, published: set[Path]) -> str:
    target = match.group(2)
    if urlsplit(target).scheme or target.startswith(("#", "/")):
        return match.group(0)
    path, _, fragment = target.partition("#")
    resolved = (source.parent / path).resolve()
    if resolved in published:
        return match.group(0)
    if not resolved.exists():
        raise ValueError(f"Broken documentation link in {source}: {target}")
    rewritten = REPO + resolved.relative_to(ROOT).as_posix()
    if fragment:
        rewritten += "#" + fragment
    return match.group(1) + "(" + rewritten + ")"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / ".physlint/docs-site")
    args = parser.parse_args()
    published = {(ROOT / "docs" / name).resolve() for name in PAGES}
    with tempfile.TemporaryDirectory(prefix="physlint-docs-") as temporary:
        stage = Path(temporary)
        for name in PAGES:
            source = ROOT / "docs" / name
            destination = stage / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            text = re.sub(
                r"(\[[^\]]*\])\(([^)]+)\)",
                lambda match, source=source: rewrite_link(match, source, published),
                source.read_text(encoding="utf-8"),
            )
            destination.write_text(text, encoding="utf-8")
        shutil.copy2(ROOT / "llms.txt", stage / "llms.txt")
        shutil.copytree(ROOT / "schemas", stage / "schemas")
        config = load_config(
            config_file=str(ROOT / "mkdocs.yml"), docs_dir=str(stage), site_dir=str(args.output.resolve())
        )
        build(config)
    print(args.output.resolve())


if __name__ == "__main__":
    main()
