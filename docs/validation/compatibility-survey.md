# LeRobot compatibility survey

Status: first wave, 2026-08-30  
Tier: compatibility observations — **not the public release gate**

The release gate remains the four pinned snapshots in [`validation/manifest.yaml`](../../validation/manifest.yaml). This survey asks a different question: does the LeRobot v3 adapter stay honest across embodiments, producers, and cadences that those four rows do not cover?

It does not attempt to validate Hugging Face robotics data. Hub-scale crawls measure repository hygiene, not Physlint trust.

## Method

1. Screen Hub candidates from metadata only (`meta/info.json`, size, version, robot, FPS, license/gate).
2. Keep a snapshot only when it fills an empty diversity cell and is small enough to review findings by hand.
3. Pin the exact revision. Download into `validation/.work/survey/`, which is gitignored.
4. Run the default `physlint check`. Record sanitized reports. Do not require a pass.
5. For published v2.x layouts, download only `meta/info.json` and prove discovery fails closed.
6. Classify findings against source values before promoting any row into the release gate.

## First-wave cells

| Cell | Snapshot |
|---|---|
| Official 10 FPS / 2D | `lerobot/pusht` |
| Official xArm / 15 FPS | `lerobot/xarm_lift_medium` |
| Official humanoid / 50 FPS | `lerobot/unitreeh1_two_robot_greeting` |
| Official SO-100 / 30 FPS | `lerobot/svla_so100_pickplace` |
| Community bimanual / 50 FPS | `macrodata/aloha_static_battery_ep000_004` |
| Industrial arm / 6 FPS | `wenyixu101/ur10e-robotiq-2f85` |
| Community SO-101 / 25 FPS | `wenyixu101/so101-pick-and-place` |
| Reachy / 60 FPS | `tavis-benchmark/tavis-head-sample-reachy2` |
| Mobile base / 30 FPS | `vietnguyen28/lekiwi_go2` |
| NVIDIA Franka suite | `nvidia/LIBERO_LeRobot_v3` (`libero_spatial`) |
| Fail-closed v2.0 / v2.1 | Koch, Reachy kitchen, RoboTwin, large SO-101 |

Deferred on purpose: official mobile Aloha with `observation.effort` (8.6 GB), 1080p LeKiwi (3.9 GB), 10 GB SO-101 sim, 60 GB BridgeData V2, and multi-terabyte Hub dumps. Those belong in a later size/memory wave, not this survey.

## Claims that stay false

- “Physlint validated Hugging Face robotics datasets.”
- “N / M Hub datasets pass.”
- “N terabytes scanned.”

After this wave the honest statement is: the release gate is unchanged; a stratified public survey of N revision-pinned v3 snapshots plus M version-edge screens is committed under `validation/reports/lerobot-survey-2026-08-30/`.

## Reproduce

```bash
python -m pip install -e '.[video,dev]'
python -m pip install huggingface_hub
python -m validation.survey_harness
```

Use `--only pusht --only koch-v21` to rerun one cell. Pass `--dataset-root ID=PATH` for an offline snapshot. The survey writes sanitized JSON next to `summary.json`; it does not update README release-gate counts.

## Results

First wave, Physlint `0.3.0`, run `lerobot-survey-2026-08-30`.

Checked snapshots: **5 passed, 5 failed, 0 errored** after the string-`names` adapter fix. Version-edge screens: **5/5 rejected**. Coverage: 1,678 episodes and 182,128 frames. The four-snapshot release gate is unchanged.

| Snapshot | Result | Applicable | Findings | Classification |
|---|---|---:|---:|---|
| `lerobot/pusht` | Fail | 15 | 50 (capped) | Likely false positive. 2D low-texture sim; 6–8 frame freezes with `motion_fraction` 1.0 against a 0.5 pixel MAD. |
| `lerobot/xarm_lift_medium` | Pass | 15 | 0 | Clean official xArm / 15 FPS. |
| `lerobot/unitreeh1_two_robot_greeting` | Pass | 15 | 0 | Clean official humanoid / 50 FPS. |
| `lerobot/svla_so100_pickplace` | Pass | 15 | 0 | Clean official SO-100 / 30 FPS. |
| `macrodata/aloha_static_battery_ep000_004` | Pass | 15 | 0 | Clean community bimanual / 50 FPS. |
| `wenyixu101/ur10e-robotiq-2f85` | Fail | 15 | 4 | Review. Four 6-frame holds at 6 FPS (~1 s) during motion; possible sim hold. |
| `wenyixu101/so101-pick-and-place` | Fail | 15 | 50 (capped) | Likely false positive. All cited ranges are the wrist camera, often 40+ frames, `motion_fraction` ~0.4. |
| `tavis-benchmark/tavis-head-sample-reachy2` | Fail | 5 | 3 | Confirmed defect. Episode metadata names `file-001/002/004.parquet`; the Hub tree only publishes `file-000.parquet`. |
| `vietnguyen28/lekiwi_go2` | Pass | 15 | 0 | Clean community mobile base. |
| `nvidia/LIBERO_LeRobot_v3` `libero_spatial` | Fail | 15 | 1 | Review. One 6-frame freeze at an episode start, `motion_fraction` 0.4. |

### Version-edge screens

Discovery rejected `v2.0` and `v2.1` metadata for Koch, Reachy kitchen, RoboTwin, and the large SO-101 pi0.5 corpus. That is the required fail-closed behavior.

### Product issues

1. **Fixed — string feature names.** Reachy stores `action.names` as `"env actions"`. Discovery previously raised a Pydantic `ValidationError`. The adapter now coerces a string name to a one-element list and wraps other invalid feature declarations as `AdapterError`.
2. **Open — frozen-frame defaults on 2D / wrist / episode-start holds.** Motion correlation is not enough when pixel MAD stays below 0.5. Do not change the default contract from this wave alone; gather more wrist-camera and 2D-sim cases first.
3. **Open — 50-finding cap.** PushT and the SO-101 teleop set both hit the cap, so the true freeze count is unknown.

No failing survey row is promoted into the release gate. Sanitized reports are in [`validation/reports/lerobot-survey-2026-08-30/`](../../validation/reports/lerobot-survey-2026-08-30/).
