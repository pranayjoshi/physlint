# Physlint 0.4.0

This release adds native LeRobot v2.0/v2.1 readers, runtime diagnostics, uniform JSON write results for `init` and `baseline`, direct revision-qualified Hub sources, safe configuration-plugin defaults, schemas and agent guidance, and a reusable GitHub Action.

## Evidence

Historical reports retain their original tool versions. The [0.4.0 verification directory](https://github.com/pranayjoshi/physlint/tree/master/validation/reports/release-0.4.0) records fresh runs against the pinned LeRobot v3 and MCAP/ROS 2 sources, plus v2 public snapshots and controlled corruption checks.

All four pinned v3 sources passed, and all three v3 corruption recipes were detected. All four MCAP/ROS 2 cases matched their expected outcomes, including the deliberately defective conformance fixture. Two public v2 sources passed without findings or errors: 52 episodes and 16,631 frames across v2.0 and v2.1. Synthetic tests additionally exercise both v2 versions, independent episode videos, injected NaNs, malformed metadata, and missing files.

Public examples establish scoped compatibility; they do not certify every dataset using that format. The [evidence atlas](https://physlint.com) includes historical release-gate and survey observations and is not a universal quality ranking.

## Deferred integrations

MCP, Robomimic HDF5, and RLDS/TFDS remain deferred. The CLI's versioned JSON and Python API already provide an integration path for agents. No reproducible format-specific requests were present in the repository issue tracker during this release assessment.

An adapter proposal should supply a revision-pinned source, a healthy case and a real failure mode, canonical stream/episode mappings, bounded iteration, and controlled corruption tests. MCP should be added when a named client workflow needs tool discovery or transport beyond the existing CLI/API. These criteria and the [roadmap](roadmap.md) keep the next implementation tied to an actual user.
