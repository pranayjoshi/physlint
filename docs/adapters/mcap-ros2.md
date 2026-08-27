# MCAP and ROS 2 adapter boundary

Status: implemented in the `0.2.0a1` development line and field-tested on a revision-pinned ARX X5 robot recording.

Physlint treats MCAP as a recording container, not as a training-dataset schema. The generic profile checks portable container and channel properties. The ROS 2 profile adds semantics only when the file declares `profile=ros2` or the user explicitly selects it.

## Discovery

Accepted sources:

- a standalone `.mcap` file with valid MCAP magic;
- a directory containing exactly one `.mcap` file.

A directory with multiple MCAP files is rejected because silently selecting or merging split bags would change the meaning of timing and summary checks. A `.db3` rosbag2 source is rejected with `ros2 bag convert` guidance.

## Scan behavior

The adapter performs one read-only scan and shares its observations across all applicable rules. CRCs are validated when available. Message payloads are not retained.

Timing memory is bounded per channel: rollback, duplicate, sequence-break, and maximum-gap counts remain exact, while local cadence inference uses a deterministic reservoir of at most 4,096 positive intervals. Finding examples and decode/semantic error examples are capped at 50 per channel.

## ROS 2 semantics

Embedded `ros2msg` schemas and CDR payloads are decoded through `mcap-ros2-support`; a ROS installation is not required. Built-in invariants currently cover:

- `sensor_msgs/msg/JointState` name/value dimensions;
- `sensor_msgs/msg/Image` payload size;
- `sensor_msgs/msg/CompressedImage` presence and optional OpenCV decode;
- `tf2_msgs/msg/TFMessage` empty/self-referencing frames and stable child parents;
- any decoded message with a standard header for configured header/log skew.

Required topics, topic rates, gap tolerance, and clock-skew tolerance are user contracts. They are not guessed. A required topic must contain at least one message; a zero-message declaration does not satisfy the contract.

## Unsupported cases

- split or multi-file MCAP bags;
- native rosbag2 SQLite and ROS 1 bag parsing;
- arbitrary application-specific message invariants;
- automatic conversion of topics into training actions, observations, cameras, or episodes;
- image black/frozen-frame analysis inside MCAP;
- replay, repair, source mutation, or safety certification.
