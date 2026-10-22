"""Render publication-safe Physlint launch images and a captioned MP4.

Run with ``uv run --extra launch python scripts/render_launch_video.py``.
The renderer never records the desktop and never reads shell history, so the
result cannot accidentally expose notifications, usernames, or local paths.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import av
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
EXPORTS = ROOT / "docs" / "assets" / "launch" / "exports"
WIDTH, HEIGHT, FPS = 1920, 1080, 30

INK = "#eef2ff"
MUTED = "#a8b0c7"
CYAN = "#6ddcff"
GREEN = "#8fe388"
RED = "#ff7d91"
PURPLE = "#c6a7ff"
BG = "#0b1020"
PANEL = "#151b30"


def _font(size: int, *, bold: bool = False, mono: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if mono:
        candidates += [
            Path("/System/Library/Fonts/SFNSMono.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"),
        ]
    elif bold:
        candidates += [
            Path("/System/Library/Fonts/SFNS.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]
    else:
        candidates += [
            Path("/System/Library/Fonts/SFNS.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _base() -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BG)
    draw = ImageDraw.Draw(image)
    draw.ellipse((-260, -360, 840, 740), fill="#111a38")
    draw.ellipse((1350, 650, 2300, 1500), fill="#151238")
    return image


def _brand(draw: ImageDraw.ImageDraw) -> None:
    draw.rounded_rectangle((88, 68, 132, 112), radius=10, fill=CYAN)
    draw.rectangle((101, 81, 143, 123), fill=PURPLE)
    draw.text((164, 69), "physlint", font=_font(42, bold=True), fill=INK)
    draw.text((164, 116), "robot data integrity before training", font=_font(23), fill=MUTED)


def _footer(draw: ImageDraw.ImageDraw, caption: str, step: int) -> None:
    draw.rounded_rectangle((72, 910, 1848, 1020), radius=28, fill="#0d1428", outline="#2b3655", width=2)
    draw.text((112, 940), caption, font=_font(32, bold=True), fill=INK)
    x = 1574
    for index in range(6):
        color = CYAN if index <= step else "#34405f"
        draw.rounded_rectangle((x + index * 36, 953, x + index * 36 + 24, 965), radius=6, fill=color)


def _title_card() -> Image.Image:
    image = _base()
    draw = ImageDraw.Draw(image)
    _brand(draw)
    draw.text((130, 332), "Bad robot data", font=_font(92, bold=True), fill=INK)
    draw.text((130, 438), "is expensive.", font=_font(92, bold=True), fill=CYAN)
    draw.text((136, 578), "Catch broken schemas, clocks, numeric streams, and video", font=_font(34), fill=MUTED)
    draw.text((136, 626), "before they consume training time.", font=_font(34), fill=MUTED)
    _footer(draw, "Local-first validation for physical-AI data", 0)
    return image


def _terminal_card(*, corrupt: bool) -> Image.Image:
    image = _base()
    draw = ImageDraw.Draw(image)
    _brand(draw)
    draw.rounded_rectangle((100, 190, 1820, 845), radius=28, fill="#090d19", outline="#323b57", width=3)
    for x, color in ((138, "#ff6b75"), (178, "#ffd45f"), (218, "#5fdb83")):
        draw.ellipse((x, 223, x + 24, 247), fill=color)
    mono = _font(32, mono=True)
    small = _font(27, mono=True)
    draw.text((138, 290), "$ physlint demo", font=mono, fill=INK)
    if corrupt:
        lines = [
            ("CORRUPTED DATASET", RED, mono),
            ("Result: FAILED", RED, mono),
            ("Rule:   numeric.finite_values", CYAN, mono),
            ("Where:  episode_000000 · action · sample 4 · dimension 0", INK, small),
            ("Why:    Non-finite values poison losses and model parameters.", MUTED, small),
            ("Fix:    Recollect the sample and repair the producing transform.", MUTED, small),
        ]
    else:
        lines = [
            ("CLEAN DATASET", GREEN, mono),
            ("Result: PASSED", GREEN, mono),
            ("Rules:  12 passed · 0 failed · 0 errored", CYAN, mono),
            ("Scope:  1 episode · 8 frames · LeRobot v3", INK, small),
            ("Mode:   safe by default · installed plugins only", MUTED, small),
        ]
    y = 370
    for text, color, font in lines:
        draw.text((138, y), text, font=font, fill=color)
        y += 75
    caption = (
        "Exact rule, episode, stream, sample, and remediation"
        if corrupt
        else "One command validates a healthy and corrupted dataset"
    )
    _footer(draw, caption, 2 if corrupt else 1)
    return image


def _asset_card(asset: Path, *, caption: str, step: int, title: str) -> Image.Image:
    image = _base()
    draw = ImageDraw.Draw(image)
    _brand(draw)
    draw.text((100, 172), title, font=_font(44, bold=True), fill=INK)
    source = Image.open(asset).convert("RGB")
    source.thumbnail((1640, 620), Image.Resampling.LANCZOS)
    x = (WIDTH - source.width) // 2
    y = 235 + (610 - source.height) // 2
    shadow = Image.new("RGBA", (source.width + 36, source.height + 36), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        shadow.getbbox() or (0, 0, shadow.width, shadow.height), radius=24, fill="#00000088"
    )
    image.paste(shadow.convert("RGB"), (x - 18, y - 12))
    image.paste(source, (x, y))
    _footer(draw, caption, step)
    return image


def _cta_card() -> Image.Image:
    image = _base()
    draw = ImageDraw.Draw(image)
    _brand(draw)
    draw.text((130, 300), "Validate before you train.", font=_font(76, bold=True), fill=INK)
    draw.text((130, 410), "pip install physlint", font=_font(47, mono=True), fill=CYAN)
    draw.rounded_rectangle((130, 520, 1280, 625), radius=22, fill=PANEL, outline="#374567", width=2)
    draw.text((170, 547), "github.com/pranayjoshi/physlint", font=_font(37, mono=True), fill=INK)
    draw.text((136, 690), "Try your dataset · add it to CI · contribute an adapter", font=_font(33), fill=MUTED)
    _footer(draw, "Open source · local first · evidence backed", 5)
    return image


def _ease(value: float) -> float:
    return value * value * (3 - 2 * value)


def _animate(card: Image.Image, progress: float) -> Image.Image:
    # A restrained 1.5% push-in keeps static evidence readable on small screens.
    zoom = 1.0 + 0.015 * _ease(progress)
    resized = card.resize((round(WIDTH * zoom), round(HEIGHT * zoom)), Image.Resampling.LANCZOS)
    x = (resized.width - WIDTH) // 2
    y = (resized.height - HEIGHT) // 2
    return resized.crop((x, y, x + WIDTH, y + HEIGHT))


def _render_video(cards: list[tuple[Image.Image, float]], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    container = av.open(str(output), mode="w")
    stream = container.add_stream("libx264", rate=FPS)
    stream.width = WIDTH
    stream.height = HEIGHT
    stream.pix_fmt = "yuv420p"
    stream.options = {"crf": "20", "preset": "medium", "movflags": "+faststart"}
    fade_frames = 12
    previous: Image.Image | None = None
    for card, seconds in cards:
        count = round(seconds * FPS)
        for frame_index in range(count):
            frame = _animate(card, frame_index / max(1, count - 1))
            if previous is not None and frame_index < fade_frames:
                alpha = _ease(frame_index / fade_frames)
                frame = Image.blend(previous, frame, alpha)
            video_frame = av.VideoFrame.from_ndarray(np.asarray(frame), format="rgb24")
            for packet in stream.encode(video_frame):
                container.mux(packet)
        previous = _animate(card, 1.0)
    for packet in stream.encode():
        container.mux(packet)
    container.close()


def _save_publication_images(clean: Image.Image, corrupt: Image.Image) -> None:
    EXPORTS.mkdir(parents=True, exist_ok=True)
    clean.crop((100, 190, 1820, 845)).save(EXPORTS / "clean-validation.png", optimize=True)
    corrupt.crop((100, 190, 1820, 845)).save(EXPORTS / "controlled-nan-failure.png", optimize=True)


def _save_compatibility_image() -> None:
    image = Image.new("RGB", (1600, 900), "#111111")
    draw = ImageDraw.Draw(image)
    draw.text((64, 52), "Format compatibility", font=_font(50, bold=True), fill=INK)
    draw.text((64, 112), "Implemented adapters and explicit boundaries", font=_font(27), fill=MUTED)
    columns = (64, 540, 1130)
    headers = ("FORMAT", "STATUS", "INTENDED MODE")
    for x, header in zip(columns, headers, strict=True):
        draw.text((x, 190), header, font=_font(22, bold=True), fill=CYAN)
    rows = [
        ("LeRobot Dataset v3.x", "Alpha — implemented and publicly validated", "Training datasets"),
        ("Generic MCAP", "Alpha preview — implemented and validated", "Container integrity"),
        ("ROS 2 over MCAP", "Alpha preview — implemented and validated", "Topic and semantic checks"),
        ("Robomimic HDF5", "Planned", "Demonstration datasets"),
        ("RLDS / TFDS", "Researching", "Episode and step datasets"),
        ("ROS bag2 SQLite / ROS 1 bag", "Researching", "Recordings"),
    ]
    y = 250
    for index, row in enumerate(rows):
        fill = "#171717" if index % 2 == 0 else "#202020"
        draw.rounded_rectangle((48, y - 18, 1552, y + 76), radius=10, fill=fill)
        for x, text in zip(columns, row, strict=True):
            color = GREEN if "implemented" in text else INK
            draw.text((x, y), text, font=_font(24), fill=color)
        y += 102
    draw.text(
        (64, 846),
        "Claims are adapter-specific; planned formats are never reported as supported.",
        font=_font(23),
        fill=MUTED,
    )
    image.save(EXPORTS / "format-compatibility.png", optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=EXPORTS / "physlint-launch.mp4",
        help="MP4 output path",
    )
    args = parser.parse_args()

    clean = _terminal_card(corrupt=False)
    corrupt = _terminal_card(corrupt=True)
    title = _title_card()
    _save_publication_images(clean, corrupt)
    _save_compatibility_image()
    title.save(EXPORTS / "physlint-launch-poster.png", optimize=True)
    cards = [
        (title, 4),
        (clean, 7),
        (corrupt, 11),
        (
            _asset_card(
                EXPORTS / "validation-summary.png",
                title="Reproducible public evidence",
                caption="4 pinned snapshots · 31,258 frames · 3/3 controlled corruptions",
                step=3,
            ),
            8,
        ),
        (
            _asset_card(
                EXPORTS / "format-compatibility.png",
                title="One contract, format-aware checks",
                caption="LeRobot v3, generic MCAP, and ROS 2 over MCAP implemented",
                step=4,
            ),
            8,
        ),
        (_cta_card(), 7),
    ]
    _render_video(cards, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
