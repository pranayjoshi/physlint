# MCAP/ROS validation proposal

Status: design proposal; no MCAP support is included in `0.1.0a1`.

MCAP is a heterogeneous timestamped channel container rather than a training-dataset schema. Physlint should therefore provide useful recording checks without pretending to know which channel represents an action, observation, camera, or episode boundary.

## Layer 1: format-level checks without a profile

- Header/footer, chunk, summary, and index readability
- Referenced schema availability and supported message encoding
- Per-channel log/publish timestamp monotonicity
- Duplicate timestamps, large gaps, unstable rates, and recording truncation
- Image/compressed-image decode failures and black-frame runs
- Attachment and metadata inventory
- Privacy-safe evidence containing channel, time, schema, and source offsets

## Layer 2: ROS profile checks

- Required topic presence
- ROS clock discontinuities
- `/tf` and `/tf_static` parent/child consistency and long transform gaps
- `sensor_msgs/Image` and `CompressedImage` cadence/decode
- `JointState` name/value dimension agreement
- Header timestamp versus MCAP log-time skew

## Layer 3: training-semantic profiles

```yaml
adapter: mcap
profile:
  action: /robot/action
  state: /joint_states
  cameras:
    - /camera/front/image_raw
  episode_boundary:
    topic: /episode_event
    start_value: START
    end_value: END
```

Profiles must be explicit, versioned, and report their mapping. With no episode markers, a file may be treated as one recording session for transport checks but must not be described as a training episode.

## Design-partner inputs needed

- A small immutable healthy MCAP
- A representative topic/schema inventory
- How collection runs and training episodes are segmented
- Known dropped-message, clock, image, or shutdown failures
- Expected healthy rates and required channels
- Permission to commit sanitized reports and corruption recipes

Open an adapter request using the repository issue template; do not upload private robot recordings to a public issue.
