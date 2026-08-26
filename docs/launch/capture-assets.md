# Manual video, screenshot, and publication-data capture

Use this runbook after `0.1.0a1` is committed and before publishing launch posts.

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

## 4. Record the 35–45 second launch video

QuickTime screen recording is sufficient on macOS; OBS is useful when you need precise 1080p/30 fps output. Record locally with microphone disabled unless you are intentionally narrating.

Storyboard:

| Time | Visual | On-screen message |
|---:|---|---|
| 0–4 s | Title card | “Bad robot data is expensive.” |
| 4–11 s | Run clean check | “Validate locally before training.” |
| 11–22 s | Run NaN corruption check | “Exact rule, episode, stream, and sample evidence.” |
| 22–30 s | Show validation SVG | “4 public snapshots · 31,258 frames · 3/3 corruptions.” |
| 30–38 s | Show compatibility matrix | “LeRobot v3 alpha. MCAP/ROS and Robomimic next.” |
| 38–45 s | Repository and CTA | “Try a dataset or become an MCAP design partner.” |

Record each segment as a separate take. Trim pauses and loading time; do not artificially alter command output. Use simple cuts, no rapid zooms, and captions that remain readable on a phone. Export one 1920×1080 H.264 MP4 at 30 fps, then create platform crops only from that master.

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
