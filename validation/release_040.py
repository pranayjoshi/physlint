"""Run pinned 0.4.0 evidence without overwriting historical reports.

Run with python -m validation.release_040. Public sources use the standard Hub
cache. Only metadata, sanitized findings, and checksums are published.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import yaml

from physlint import __version__
from physlint.config import CacheSettings, Config
from physlint.engine.discovery import discover
from physlint.engine.runner import run_validation
from physlint.sources import resolve_source
from validation import harness, mcap_harness

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "reports/release-0.4.0"
V2_SOURCES = (
    ("so101-v21", "rshoff/lerobot", "876192fd1bad1ef4992a0b2f059be0f90718d935"),
    ("koch-v20", "rgarreta/koch_pick_place_lego_v8", "bdaa738541e52caa64508283b7a8eef7bfcfd9e8"),
)


def main() -> None:
    if __version__ != "0.4.0":
        raise RuntimeError("This harness verifies Physlint 0.4.0; use that release to reproduce")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="physlint-release-040-") as temporary:
        work = Path(temporary)
        manifest = harness.load_manifest(ROOT / "manifest.yaml")
        manifest.update(run_id="release-0.4.0-lerobot", physlint_version=__version__)
        manifest_path = OUTPUT / "lerobot-manifest.yaml"
        manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
        overrides = []
        for record in manifest["datasets"]:
            source = resolve_source(f"hf://datasets/{record['repo_id']}@{record['revision']}")
            overrides.append(f"{record['id']}={source.path}")
        harness.run(
            argparse.Namespace(
                manifest=manifest_path,
                output=OUTPUT / "lerobot-v3",
                work=work / "lerobot-v3",
                cache_dir=None,
                dataset_root=overrides,
            )
        )
        print("LeRobot v3 gate passed", flush=True)
        mcap_manifest = mcap_harness.load_manifest(ROOT / "mcap_manifest.yaml")
        mcap_manifest.update(run_id="release-0.4.0-mcap", physlint_version=__version__)
        mcap_path = OUTPUT / "mcap-manifest.yaml"
        mcap_path.write_text(yaml.safe_dump(mcap_manifest, sort_keys=False), encoding="utf-8")
        recording = []
        for record in mcap_manifest["public_recordings"]:
            cached = ROOT / ".work/mcap-ros2" / f"{record['id']}.mcap"
            if cached.is_file():
                recording.append(f"{record['id']}={cached}")
        mcap_harness.run(
            argparse.Namespace(
                manifest=mcap_path,
                output=OUTPUT / "mcap",
                work=work / "mcap",
                recording=recording,
            )
        )
        print("MCAP and ROS 2 gate passed", flush=True)
        v2_output = OUTPUT / "lerobot-v2"
        v2_output.mkdir(exist_ok=True)
        rows = []
        for identifier, repo, revision in V2_SOURCES:
            identity = f"hf://datasets/{repo}@{revision}"
            source = resolve_source(identity)
            dataset = discover(source.path)
            report = run_validation(
                dataset,
                Config(cache=CacheSettings(enabled=False)),
                extra_rules=[],
                allow_config_plugins=False,
                reported_dataset_path=identity,
            ).model_copy(update={"source_revision": revision})
            if report.summary.errored:
                raise AssertionError(f"Public v2 source could not be completely checked: {identifier}")
            digest = harness.write_report(report, v2_output / f"{identifier}.json")
            rows.append(
                {
                    "id": identifier,
                    "source": identity,
                    "format": dataset.inventory.format_version,
                    "episodes": len(dataset.inventory.episodes),
                    "frames": dataset.inventory.total_frames,
                    "status": report.status,
                    "findings": report.summary.findings,
                    "errored": report.summary.errored,
                    "artifact": f"{identifier}.json",
                    "sha256": digest,
                }
            )
            print(identifier, report.status, report.summary.model_dump(), flush=True)
        (v2_output / "summary.json").write_text(
            json.dumps(
                {
                    "physlint_version": __version__,
                    "tier": "public-v2-compatibility",
                    "results": rows,
                    "controlled_cases": "tests/test_lerobot_v2.py: clean, NaN, video, malformed v2.0/v2.1 metadata",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    hashes = {
        str(path.relative_to(OUTPUT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(OUTPUT.rglob("*.json"))
        if path.name != "checksums.json"
    }
    (OUTPUT / "checksums.json").write_text(json.dumps(hashes, indent=2) + "\n", encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
