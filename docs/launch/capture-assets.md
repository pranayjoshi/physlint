# Manual video, screenshot, and publication-data capture

Use this runbook after the intended release commit is finalized and before publishing launch posts.

## 1. Regenerate the evidence

From the repository root:

```bash
python -m pip install -e '.[video,dev]'
python -m pip install huggingface_hub
python -m validation.harness
python -m validation.render_assets
magick -background none docs/assets/launch/validation-summary.svg docs/assets/launch/validation-summary.png
```

The first command set creates:

- `validation/reports/real-data-2026-08-24/clean-*.json`
- `validation/reports/real-data-2026-08-24/corruption-*.json`
- `validation/reports/real-data-2026-08-24/summary.json`
- `validation/reports/real-data-2026-08-24/summary.csv`
- `validation/.work/corruption-*` reproducible working copies
- `docs/assets/launch/validation-summary.svg`
- `docs/assets/launch/validation-summary.png` when ImageMagick is installed

Before publishing, inspect the summary and scan for accidental local paths or credentials:

```bash
python -m json.tool validation/reports/real-data-2026-08-24/summary.json
rg -n '/Users/|/home/|C:\\|hf_[A-Za-z0-9]|token' validation/reports docs/assets/launch
git diff --check
```

Expected publication facts are 4/4 clean snapshots passing, 3/3 corruptions detected, 74 episodes, and 31,258 frames. Stop if regenerated values differ; investigate rather than editing the outputs by hand.

## 2. Prepare a safe terminal

1. Enable Do Not Disturb and close email, chat, password managers, cloud consoles, and private repositories.
2. Open a new terminal profile with a plain dark background, 22–26 pt monospace text, and no translucent background.
3. Set the window to approximately 120 columns by 32 rows. Record a 1920×1080 master when possible.
4. Use a prompt that shows only `$`; hide username, hostname, current branch credentials, and full home-directory paths.
5. Clear command history from the visible window with `clear`; do not clear your shell's saved history unless you independently want to.
6. Never display Hugging Face tokens. The validation sources are public and require no token in the recording.

Create short display paths without changing source data. Use the repository helper so colored/multi-line Hugging Face CLI output cannot become part of the symlink target:

```bash
python -m validation.prepare_demo
```

If you already ran the older shell snippet and received a path containing `✓ Downloaded` or line breaks, repair it safely with:

```bash
python -m validation.prepare_demo --force
```

`--force` replaces symlinks only. It refuses to delete a real directory.

## 3. Capture the screenshots

Capture PNG, not JPEG, so terminal text remains sharp. On macOS use Shift–Command–4 and then Space to capture the terminal window, or Shift–Command–5 for a selected region. Do not capture the desktop, menu-bar account name, notifications, or unrelated tabs.

### Screenshot A: clean result

```bash
clear
physlint check /tmp/physlint-demo/clean --json-output /tmp/physlint-demo/clean-report.json
```

Wait for the final result, then capture the command, dataset identity, PASS result, rule counts, and report destination. Crop empty space but retain the command so the image is credible and reproducible.

### Screenshot B: controlled defect

```bash
clear
physlint check /tmp/physlint-demo/nan --json-output /tmp/physlint-demo/nan-report.json
```

Capture the FAIL result and `numeric.finite_values` evidence. Confirm the screenshot contains no raw state vector or source machine path.

### Screenshot C: evidence card

Open `docs/assets/launch/validation-summary.png` at 100% zoom. Preserve the SVG as the canonical asset; PNG is the GitHub/social distribution derivative.

### Screenshot D: compatibility matrix

Render the README on GitHub and capture the format compatibility table. The visible distinction between “implemented” and “planned” prevents broad positioning from becoming a false support claim.

Store selected source captures in `docs/assets/launch/source/` and final crops in `docs/assets/launch/export/`. Do not commit redundant takes or video source files unless repository size has been considered.

## 4. Render the 18-second launch video

The renderer runs the built-in demo and extracts the actual corrupted action values and finding. Each render stops if the demo no longer produces one expected defect. It draws the animation directly, without capturing a desktop:

```bash
uv run --extra launch python scripts/render_launch_video.py
```

It writes two silent H.264 MP4s at 30 fps: `physlint-launch.mp4` (1920×1080) and `physlint-launch-social.mp4` (1080×1350), plus the poster and `physlint-launch-evidence.json`, under `docs/assets/launch/exports/`. The separate WebVTT transcript is maintained alongside them. Select a single layout with `--format landscape` or `--format social`, or send a render to another directory with `--output-dir PATH`.

Storyboard:

| Time | Visual | On-screen message |
|---:|---|---|
| 0–3 s | Scan the action values and stop at NaN | “One bad sample. Catch it before training.” |
| 3–7 s | Type the demo command; reveal pass/fail | “Check the dataset.” |
| 7–12 s | Reveal the finding and its exact location | “Found. Sample 4.” |
| 12–18 s | Product name, supported formats, and demo link | “Lint before you train.” |

The clip uses large typography, a moving sample cursor, command typing, and sequential finding reveals. It depicts a synthetic corruption with edited timing. It makes no claim about training outcomes or scan speed. Layouts are rendered separately so feed text remains legible.

Listen once with audio, watch once muted, and watch once on a phone. Verify every technical claim against `summary.json` immediately before upload.

## 5. Prepare publication data

Use `summary.csv` for charts and tables. Keep these columns visible in any published derivation:

- Repository and pinned revision
- Robot/embodiment
- Clean or controlled corruption status
- Applicable-rule count and finding count
- Measured rule time
- Artifact filename and SHA-256

When discussing speed, identify the before/after run and hardware context. The current durable run measured 4.42–14.59× against the recorded baseline on the three video datasets; prefer that scoped statement over an unqualified performance claim.

Do not publish raw robot frames merely because the dataset is public. Check the dataset license, attribution requirements, depicted people, lab details, screens, and location information first. The terminal-only video avoids that risk.

## 6. Final pre-upload review

- Install command works from the published wheel.
- Repository and issue links are public.
- Captions accurately distinguish implemented and planned adapters.
- Alt text describes the result rather than repeating decorative text.
- No API key, username, private path, browser bookmark, notification, or personal message is visible.
- Dataset publishers are linked and attributed in the technical article.
- You are available for questions for several hours after each community post.
