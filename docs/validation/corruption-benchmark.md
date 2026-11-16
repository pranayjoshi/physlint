# Corruption benchmark

Status: second measurement, 2026-10-31, on the code released as 0.5.0, with 49 rules. The first measurement, with 36 rules, is kept for comparison.

The benchmark asks two questions per defect type: does Physlint report it, and does it stay quiet when nothing is wrong? Full results are in [`report.md`](../../validation/reports/corruption-benchmark-2026-10-31-v2/report.md), with per-trial outcomes in [`trials.csv`](../../validation/reports/corruption-benchmark-2026-10-31-v2/trials.csv). The earlier run is in [`corruption-benchmark-2026-10-31`](../../validation/reports/corruption-benchmark-2026-10-31/report.md).

## Results

Macro detection averages per defect type, so a defect with many severity levels does not count more than one with a single level.

| Split | What it contains | Before (36 rules) | Now (49 rules) | Benign false alarms |
|---|---|---:|---:|---:|
| **Final** | 5 public datasets reserved from tuning | **63%** | **92%** | 1/18 |
| Dev | 10 public datasets used to tune thresholds | – | 89% | 1/37 |
| Synthetic | LeRobot scenes and one ROS 2 recording, clean by construction | – | 93% | 0/22 |

**Shipped default: 89%.** `temporal.signal_alignment` is off by default after this run because of the false alarms below. Recomputing the same trials without it gives 89% on the final split, 87% on dev and 93% on synthetic. Detection drops mainly for `reversed_episode` (5%), `action_state_swap` (14%) and `action_shift` (50%).

Quote the final figure, together with these two:

- **Most of the gain comes from warnings.** Counting only findings that fail CI by default, detection on the final split is 66%. Statistical rules default to warnings because they report anomalies, not proof.
- **False alarms now appear as warnings.** No real dataset fails the default contract, but 9 of the 15 real datasets receive at least one warning. These have not been manually classified.

### Known weak spots

- **`temporal.signal_alignment` is noisy, so it is now opt-in.** On the final split it flagged 122 of 800 `xarm-lift` episodes and 25 of 432 `libero-spatial` episodes. This appeared only on the reserved datasets, so it was not tuned afterward. Expect this rule to need work, and fresh test data once it changes.
- **`video.frozen_frames` is improved but unresolved.** `pusht` went from 688 findings to none. It still reports 42 on `ur10e-robotiq` and 18 on `so101-teleop`. Inspected frames show no visible robot movement while recorded joint values change, which could be a real capture problem or a camera that cannot see the motion. It is now a warning.
- **Low detection remains:** `swapped_cameras` 10%, `reversed_episode` 24%, `action_state_swap` 48%, and `action_shift` 57%.
- **Some swaps cannot be detected.** When one video file holds every episode, swapping two files swaps every episode, leaving nothing to compare against.

## What changed between runs

- **New rules:** temporal start and drift, video bitstream and timeline checks, repeated frames, camera identity, and seven statistical rules calibrated from the dataset.
- **Reworked rules:** frozen-frame detection and MCAP timestamp ordering, which now ignores small reorderings and publish time.
- **Benchmark changes that affect comparison:** freezes are injected where the robot moves most, the MCAP `log_rollback` defect is now a 5 second clock reset, and synthetic scenes use smooth motion and eight episodes. The 63% and 92% come from the same 5 datasets, but these recipe changes mean the comparison is not exact.

## Method

- **Corpus:** revision-pinned snapshots in [`benchmark_manifest.yaml`](../../validation/benchmark_manifest.yaml). `reachy-head` is excluded because it has a confirmed defect.
- **Reserved datasets:** these were chosen before tuning, and thresholds were not changed after they were evaluated. They are not fully blind: their first-run results were seen earlier, and the same recipes informed the rule design.
- **Defects:** 48 LeRobot and 10 MCAP/ROS 2 types, at up to three severities, three seeds each. Recipes live in [`validation/benchmark.py`](../../validation/benchmark.py).
- **Isolation:** each trial symlinks the source into a scratch directory and replaces only the files a recipe changes.
- **Contract:** default thresholds with one change: the 50-finding cap is lifted, because it would hide the injected episode. The MCAP track also configures a required topic and a topic rate.
- **Detection:** a finding is credited only when it is new compared with the clean baseline and is on the injected episode or at dataset level. A new rule error counts as detected, reported as `failed_closed`.
- **Re-encoding control:** frame-editing recipes re-encode video, which can change findings on its own, so findings from an identity re-encode are subtracted. Affected trials are recorded as `control_masked`.

## Limits

- **The recipes are not a sample of real-world defects.** They were written with knowledge of Physlint's rules, and the rules were then written against them. The macro score says nothing about how common any defect is, or what share of real defects Physlint would catch.
- **A noisy rule can earn credit by chance.** A rule that flags many episodes is more likely to flag an injected one, so detection for `temporal.signal_alignment` is likely overstated.
- **Trials are not independent.** Seeds and severities share datasets, so the 95% intervals are narrower than they should be.
- **Clean-corpus flags are not ground truth.** A flagged public dataset may have a real defect. Only the synthetic scenes and benign transforms give certain false alarms.
- **Video coverage is uneven.** Frame-editing recipes skip video files over 64 MiB.
- **The MCAP track is thin.** It has one synthetic recording, so its 100% rates mean "works on this recording".
- **Reproducibility:** a test confirms identical output across repeated runs on a fixture. The full corpus was run once per rule set.

## Reproduce

```bash
python -m pip install -e '.[video,dev]'
python -m validation.benchmark --seeds 3
```

The benchmark never downloads anything. It uses pinned snapshots from the local Hugging Face cache and `validation/.work/survey/datasets`, or paths passed with `--dataset-root ID=PATH`, and reports any that are unavailable. Use `--split`, `--only ID`, or `--category NAME` for a partial run, and pass `--output` so a partial run does not overwrite the committed report.
