# Changelog

## 0.1.0a1 — public alpha

- Add 17 deterministic LeRobot v3 integrity rules and stable CI exit codes.
- Make maximum-gap defaults scale with declared FPS while preserving absolute overrides.
- Require aligned robot motion for frozen-camera findings.
- Share one privacy-safe video analysis pass across video rules.
- Group repeated gap and black-frame evidence.
- Preserve Hugging Face repository identity and pinned source revision.
- Separate NaN/Inf findings from null/empty stream-overlap semantics.
- Add a reproducible four-dataset and three-corruption release gate.

This alpha supports local LeRobot v3.x directories. MCAP/ROS 2 and Robomimic are roadmap items, not implemented adapters.
