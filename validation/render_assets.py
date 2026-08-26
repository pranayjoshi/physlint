"""Render a dependency-free SVG social card from committed validation metrics."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEFAULT_SUMMARY = ROOT / "reports" / "real-data-2026-08-24" / "summary.json"
DEFAULT_OUTPUT = ROOT.parent / "docs" / "assets" / "launch" / "validation-summary.svg"


def render(summary: Path, output: Path) -> None:
    data = json.loads(summary.read_text(encoding="utf-8"))
    metrics = [
        (f"{data['clean_passed']}/{data['clean_datasets']}", "clean snapshots passed"),
        (f"{data['controlled_corruptions_detected']}/{data['controlled_corruptions']}", "corruptions detected"),
        (f"{data['episodes']:,}", "episodes"),
        (f"{data['frames']:,}", "frames"),
    ]
    cards = []
    for index, (value, label) in enumerate(metrics):
        x = 70 + index * 280
        cards.append(
            f'<rect x="{x}" y="275" width="250" height="165" rx="18" fill="#151d33"/>'
            f'<text x="{x + 24}" y="345" class="metric">{value}</text>'
            f'<text x="{x + 24}" y="390" class="label">{label}</text>'
        )
    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="630" viewBox="0 0 1200 630">
  <title>Physlint public alpha validation summary</title>
  <desc>Four of four clean snapshots passed, three of three corruptions detected, 74 episodes and 31,258 frames.</desc>
  <defs>
    <linearGradient id="background" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#07111f"/>
      <stop offset="1" stop-color="#10182d"/>
    </linearGradient>
    <style>
      text {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, sans-serif; }}
      .eyebrow {{ fill: #64d8cb; font-size: 24px; font-weight: 700; letter-spacing: 2px; }}
      .title {{ fill: #f7fafc; font-size: 58px; font-weight: 760; }}
      .subtitle {{ fill: #b7c3d8; font-size: 25px; }}
      .metric {{ fill: #ffffff; font-size: 44px; font-weight: 760; }}
      .label {{ fill: #aebbd1; font-size: 18px; }}
      .footer {{ fill: #8291ab; font-size: 19px; }}
    </style>
  </defs>
  <rect width="1200" height="630" fill="url(#background)"/>
  <circle cx="1080" cy="70" r="180" fill="#2dd4bf" opacity="0.08"/>
  <text x="70" y="86" class="eyebrow">PHYSLINT · PUBLIC ALPHA</text>
  <text x="70" y="165" class="title">Robot data integrity, before training.</text>
  <text x="70" y="220" class="subtitle">Reproducible validation on pinned public LeRobot v3 snapshots</text>
  {"".join(cards)}
  <text x="70" y="535" class="footer">Local-first · privacy-safe evidence · deterministic CI exit codes</text>
  <text x="70" y="575" class="footer">github.com/pranayjoshi/physlint</text>
</svg>
"""
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    result.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return result


if __name__ == "__main__":
    arguments = parser().parse_args()
    render(arguments.summary, arguments.output)
