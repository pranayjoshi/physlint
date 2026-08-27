# Cross-format roadmap

Physlint's product boundary is physical-AI data integrity, not one storage format. The rule engine consumes canonical episodes, streams, samples, video statistics, and explicit adapter capabilities. Each adapter must preserve the source format's semantics instead of guessing them.

## Modes

- **Dataset validation** checks training-ready episode structure, actions, observations, alignment, and media.
- **Recording validation** checks transport/container integrity, channels, clocks, rates, schemas, and capture continuity before a training mapping necessarily exists.

The CLI exposes one `physlint check` workflow and discovers LeRobot directories or MCAP recordings automatically. A profile option controls generic versus ROS 2 semantics; separate commands remain unnecessary while the evidence and exit-code model is shared.

## Adapter order

1. **LeRobot v3 — alpha:** immutable public-data release gate, Parquet/MP4 streaming, episode metadata, actions, observations, timestamps, and video rules.
2. **Generic MCAP + ROS 2 — alpha preview:** container/schema/index/timing checks plus portable CDR decode and known ROS 2 message invariants. Training-semantic topic mappings remain later work.
3. **Robomimic HDF5 — planned:** demonstrations already expose actions, observations, next observations, rewards, terminal state, and masks.
4. **RLDS/TFDS — researching:** nested episode/step semantics with optional robotics profiles.
5. **ROS bag2 SQLite and ROS 1 bag — researching:** direct readers only where they add value beyond a safe MCAP conversion workflow.

## Acceptance gate for every adapter

- At least one immutable public producer/platform plus controlled positive and negative fixtures for an alpha preview; two public producers before stable support
- Healthy examples and controlled corruptions
- Explicit capability and not-applicable behavior
- Bounded-memory sample iteration
- Sanitized, reproducible reports committed under `validation/`
- Documented stream/episode assumptions and unsupported cases
- No source mutation, telemetry, or implicit network access during `check`

Demand will be evaluated by reproducible format requests, design partners, public sample availability, and recurring real failure modes—not social-media votes alone.
