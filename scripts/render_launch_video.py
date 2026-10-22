"""Render an 18-second launch clip from freshly executed demo evidence.

uv run --extra launch python scripts/render_launch_video.py
Produces landscape and 4:5 social MP4s, a poster, transcript, and evidence JSON.
Text and motion are drawn directly; no desktop capture or licensed media is used.
"""

from __future__ import annotations

import argparse
import json
import math
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import av
import numpy as np
import pyarrow.parquet as pq
from PIL import Image, ImageDraw, ImageFont

from physlint.api import check_dataset
from physlint.config import CacheSettings, Config
from physlint.demo import write_demo_dataset

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "docs/assets/launch/exports"
FPS = 30
DURATION = 18
BG = "#101114"
INK = "#f4f3ed"
MUTED = "#a6a8ae"
GREEN = "#c0f46a"
RED = "#ff775f"
MONO = (
    "/System/Library/Fonts/SFNSMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
)
SANS = (
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
)


@lru_cache(maxsize=256)
def font(size: int, mono: bool = False) -> ImageFont.FreeTypeFont:
    for path in MONO if mono else SANS:
        if Path(path).is_file():
            return ImageFont.truetype(path, size=max(1, size))
    raise RuntimeError("Install DejaVu Sans and DejaVu Sans Mono, or provide the documented macOS fonts")


def evidence() -> dict:
    """Execute the product; publish only the fields actually shown in the clip."""
    settings = Config(cache=CacheSettings(enabled=False))
    with tempfile.TemporaryDirectory(prefix="physlint-launch-") as directory:
        clean = write_demo_dataset(Path(directory) / "clean", corrupted=False)
        bad = write_demo_dataset(Path(directory) / "corrupt", corrupted=True)
        clean_report = check_dataset(clean, config=settings)
        report = check_dataset(bad, config=settings)
        findings = [finding for result in report.results for finding in result.findings]
        if clean_report.status != "passed" or report.status != "failed" or len(findings) != 1:
            raise RuntimeError("Demo contract changed; review the storyboard before publishing")
        finding = findings[0]
        if (
            clean_report.summary.errored
            or report.summary.errored
            or finding.rule_id != "numeric.finite_values"
            or finding.location.stream != "action"
            or finding.location.sample_index is None
        ):
            raise RuntimeError("Demo evidence no longer matches the finite-action storyboard")
        values = pq.read_table(bad / "data/chunk-000/file-000.parquet", columns=["action"])["action"].to_pylist()
        samples = ["NaN" if not math.isfinite(row[0]) else f"{row[0]:.1f}" for row in values]
        return {
            "kind": "synthetic controlled demo; no robot or training run is depicted",
            "command": "physlint demo",
            "physlint_version": report.physlint_version,
            "samples": samples,
            "clean_passed_rules": clean_report.summary.passed,
            "corrupted_status": report.status,
            "rule_id": finding.rule_id,
            "location": finding.location.model_dump(exclude_none=True),
            "observed": finding.observed,
            "remediation": finding.remediation,
            "plugin_policy": report.plugin_policy,
        }


@dataclass
class Canvas:
    width: int
    height: int

    def __post_init__(self) -> None:
        self.scale = min(self.width, self.height) / 1080
        self.pad = round(82 * self.scale)
        self.image = Image.new("RGB", (self.width, self.height), BG)
        self.draw = ImageDraw.Draw(self.image)
        self.right = self.width - self.pad
        self.body = self.width - 2 * self.pad

    def text(self, x: float, y: float, value: str, size: int, color: str = INK, *, mono: bool = False) -> None:
        face = font(round(size * self.scale), mono)
        # Guarantee the longest line remains inside the safe horizontal area.
        while self.draw.textlength(value, font=face) > self.right - x and face.size > 12:
            face = font(face.size - 1, mono)
        self.draw.text((round(x), round(y)), value, fill=color, font=face)

    def line(self, y: float) -> None:
        self.draw.line((self.pad, y, self.right, y), fill="#35363a", width=max(1, round(2 * self.scale)))


def frame_at(t: float, width: int, height: int, data: dict) -> Image.Image:
    c = Canvas(width, height)
    s, p, h = c.scale, c.pad, c.height
    # Sparse grid ties the numeric stream to the background without screenshots.
    for x in range(0, width, max(1, round(96 * s))):
        c.draw.line((x, 0, x, height), fill="#191a1e")
    for y in range(0, height, max(1, round(96 * s))):
        c.draw.line((0, y, width, y), fill="#191a1e")
    c.text(p, h * 0.065, "physlint", 44, GREEN)
    c.text(c.right - 280 * s, h * 0.073, "ROBOT DATA LINTER", 19, MUTED, mono=True)
    c.line(h * 0.14)

    if t < 3:
        c.text(p, h * 0.21, "One bad sample.", 99)
        c.text(p, h * 0.325, "Catch it before training.", 50, MUTED)
        reveal = min(1.0, max(0.0, (t - 0.25) / 0.8))
        bad_index = data["location"]["sample_index"]
        gap = 10 * s
        cell = (c.body - 7 * gap) / 8
        y = h * 0.52
        for index, value in enumerate(data["samples"]):
            x = p + index * (cell + gap)
            bad = index == bad_index
            color = RED if bad and reveal >= 0.6 else "#292b30"
            c.draw.rounded_rectangle((x, y, x + cell, y + 116 * s), radius=12 * s, fill=color)
            c.text(x + 12 * s, y + 32 * s, value if reveal * 8 >= index else "·", 31, BG if bad else INK, mono=True)
        # Scan the real action values, then stop on the bad sample.
        selected = min(bad_index, int(max(0, t - 0.35) * 4))
        marker_x = p + selected * (cell + gap)
        c.draw.rectangle(
            (marker_x, y - 20 * s, marker_x + cell, y - 15 * s),
            fill=RED if selected == bad_index else GREEN,
        )
        c.text(p, h * 0.72, "action stream  /  controlled NaN injection", 27, MUTED, mono=True)
        c.text(p, h * 0.85, "Synthetic demo. Actual validation evidence.", 24, MUTED)
    elif t < 7:
        local = t - 3
        c.text(p, h * 0.21, "Check the dataset.", 90)
        c.text(p, h * 0.39, "$ physlint demo"[: min(15, int(local * 22) + 1)], 62, GREEN, mono=True)
        scan = min(1.0, max(0.0, (local - 0.8) / 1.1))
        c.draw.rounded_rectangle((p, h * 0.55, c.right, h * 0.55 + 14 * s), radius=7 * s, fill="#303237")
        if scan > 0:
            c.draw.rounded_rectangle(
                (p, h * 0.55, p + max(14 * s, c.body * scan), h * 0.55 + 14 * s), radius=7 * s, fill=GREEN
            )
        if local >= 1.7:
            c.text(p, h * 0.65, "Clean: PASS", 50, GREEN)
        if local >= 2.35:
            c.text(p, h * 0.74, "Corrupted: FAIL", 50, RED)
        c.text(p, h * 0.87, "Animation timing is edited; this is not a speed benchmark.", 22, MUTED)
    elif t < 12:
        local = t - 7
        lift = max(0, 1 - min(1, local / 0.25)) * 34 * s
        c.text(p, h * 0.20 + lift, "Found. Sample " + str(data["location"]["sample_index"]) + ".", 102, RED)
        c.text(p, h * 0.345, data["rule_id"], 42, INK, mono=True)
        labels = [
            ("EPISODE", data["location"]["episode"]),
            ("STREAM", data["location"]["stream"]),
            ("DIMENSION", str(data["observed"]["non_finite_dimensions"][0])),
        ]
        for index, (label, value) in enumerate(labels):
            if local >= index * 0.25:
                y = h * (0.47 + index * 0.09)
                c.text(p, y, label, 23, MUTED, mono=True)
                c.text(p + c.body * 0.30, y - 5 * s, value, 35, mono=True)
        c.line(h * 0.78)
        c.text(p, h * 0.82, "Exact location. A fix you can act on.", 38, GREEN)
        c.text(p, h * 0.89, "Review or recollect affected samples; fix the source transform.", 23, MUTED)
    else:
        c.text(p, h * 0.22, "Lint before", 116)
        c.text(p, h * 0.34, "you train.", 116, GREEN)
        c.text(p, h * 0.54, "LeRobot v3  ·  MCAP  ·  ROS 2 over MCAP", 33, MUTED)
        c.draw.rounded_rectangle((p, h * 0.65, c.right, h * 0.65 + 100 * s), radius=14 * s, fill=GREEN)
        c.text(p + 24 * s, h * 0.65 + 25 * s, "Try the demo → GitHub README", 43, BG)
        c.text(p, h * 0.81, "github.com/pranayjoshi/physlint", 36, INK, mono=True)
        c.text(p, h * 0.90, "Open source. Runs locally. JSON for agents and CI.", 25, MUTED)

    # A timeline supplies movement and makes the short duration immediately legible.
    c.draw.rectangle((0, height - 8 * s, width * min(1, t / DURATION), height), fill=GREEN)
    return c.image


def render(path: Path, width: int, height: int, data: dict) -> None:
    # faststart is a container option, not a libx264 encoder option.
    with av.open(str(path), "w", options={"movflags": "+faststart"}) as container:
        stream = container.add_stream("libx264", rate=FPS)
        stream.width, stream.height = width, height
        stream.pix_fmt = "yuv420p"
        stream.options = {"crf": "19", "preset": "fast"}
        for index in range(DURATION * FPS):
            frame = av.VideoFrame.from_ndarray(np.asarray(frame_at(index / FPS, width, height, data)), format="rgb24")
            frame.pts = index
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=EXPORTS)
    parser.add_argument("--format", choices=["all", "landscape", "social"], default="all")
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    data = evidence()
    (args.output_dir / "physlint-launch-evidence.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    frame_at(1.5, 1920, 1080, data).save(args.output_dir / "physlint-launch-poster.png", optimize=True)
    if args.format in {"all", "landscape"}:
        render(args.output_dir / "physlint-launch.mp4", 1920, 1080, data)
    if args.format in {"all", "social"}:
        render(args.output_dir / "physlint-launch-social.mp4", 1080, 1350, data)
    print(f"Rendered {DURATION}s launch clip ({args.format}) in {args.output_dir}")


if __name__ == "__main__":
    main()
