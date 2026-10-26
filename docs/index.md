# Check robot data before training

Physlint finds structural, timing, numeric, and video defects in robot-learning datasets and MCAP recordings. It runs locally, identifies affected episodes and streams, and produces reports for humans, coding agents, and CI.

## Install and try it

Python 3.11 or newer is required.

```bash
python -m pip install "physlint[all]==0.4.0"
physlint doctor
physlint demo
```

The demo creates synthetic healthy data and a copy containing one NaN. It succeeds only when healthy data passes and the corruption is detected. It needs no account, robot, or downloaded dataset.

## Check your data

```bash
physlint inspect /path/to/dataset --format json
physlint check /path/to/dataset --format json
physlint check /path/to/recording.mcap
physlint check hf://datasets/owner/dataset@COMMIT --offline
```

Hub sources require an explicit revision. Omit `--offline` to download the public source into the standard Hub cache. Downloads can be large; no upload or telemetry is performed.

## Choose a workflow

- [CLI and diagnostics](cli.md): install checks, commands, JSON envelopes, and exit codes.
- [Quality contracts](configuration.md): thresholds, report destinations, reviewed baselines, and CI.
- [LeRobot v2 and v3](adapters/lerobot.md): supported episode, Parquet, and video layouts.
- [MCAP and ROS 2](adapters/mcap-ros2.md): container checks and topic semantics.
- [Agent guide](agents.md) and [Python API](python-api.md): machine integration.

An overall pass means the selected contract found no blocking issues. Rules with unavailable inputs are `not_run`, with a reason. Robot safety, policy quality, and task success are outside these checks.

[Explore the public evidence atlas](https://physlint.com) or [report a reproducible problem](https://github.com/pranayjoshi/physlint/issues/new/choose).
