# MCAP and ROS 2 rule contract

The MCAP adapter installs seven container rules. The ROS 2 profile adds seven semantic rules. Rules without the required configuration return `not_run` with a reason.

## Generic MCAP

| Rule | Default severity | Contract |
|---|---|---|
| `mcap.readable` | error | All records are readable and available CRCs validate. |
| `mcap.summary_consistency` | error | Summary statistics agree with observed messages, channels, schemas, attachments, and metadata. |
| `mcap.index_coverage` | notice | Efficient summary/chunk index coverage is present; fastwrite omissions remain informational. |
| `mcap.channel_schema` | error | Schema references resolve and each topic has a stable channel declaration. |
| `mcap.timestamp_order` | error | Per-channel log and publish timestamps do not move backward. |
| `mcap.duplicate_timestamps` | warning | Repeated per-channel log timestamps are visible. |
| `mcap.sequence_continuity` | warning | Non-zero sequence counters advance by one. |

## ROS 2 over MCAP

| Rule | Default severity | Contract |
|---|---|---|
| `ros2.encoding` | error | Channels use CDR with embedded `ros2msg` schemas. |
| `ros2.decode` | error | Every message decodes with its embedded definition. |
| `ros2.required_topics` | error | User-configured required topics are present. |
| `ros2.topic_gaps` | warning | Maximum topic gaps stay within an explicit per-topic cadence contract. |
| `ros2.header_clock_skew` | warning | Maximum header/log skew stays below the user-configured threshold. |
| `ros2.semantic_consistency` | error | Known JointState, Image, CompressedImage, and TF invariants hold. |
| `ros2.tf_tree` | warning | A TF child frame has one stable parent within the recording. |

`ros2.required_topics`, `ros2.topic_gaps`, and `ros2.header_clock_skew` require explicit options. Required topics must contain at least one message. Cadence is never inferred for an unconfigured topic because event-driven ROS topics do not have a stable-rate contract.
