# LeRobot adapter

Physlint 0.4.0 recognizes LeRobot v2.0, v2.1, and v3.x directories through `meta/info.json`. It selects an explicit adapter for the metadata and file layout; no conversion or source mutation is performed.

The adapter requires PyArrow `>=19.0.1`. PyArrow 19.0.0 can raise `Repetition level histogram size mismatch` on valid nested episode metadata; reinstall the project dependencies if that version is already present.

## Supported

- v3.x `info.json` feature and path templates
- Chunked Parquet episode metadata under `meta/episodes/`
- Multiple episodes sharing a Parquet file, filtered lazily by `episode_index`
- Fixed-size and regular variable-list numeric features
- Shared MP4 files segmented using per-camera episode timestamp ranges
- Metadata-first inventory without decoding video
- v2.0/v2.1 JSONL episode metadata in `meta/episodes.jsonl`
- v2 per-episode Parquet and MP4 files, including chunk boundaries derived from `chunks_size`
- Explicit Hub references such as `hf://datasets/owner/data@COMMIT`, with the `hub` extra

For v2, `data_path` and `video_path` use `episode_chunk`, `episode_index`, and `video_key`. Every episode starts at video time zero. For v3, chunk/file locators and per-camera timestamp ranges come from the episode Parquet metadata. Statistics files are not required by the current integrity rules; Physlint does not validate those aggregate statistics.

The implementation follows the [official v2.1 layout and path definitions](https://github.com/huggingface/lerobot/blob/v0.3.3/src/lerobot/datasets/utils.py) and [v2 dataset reader](https://github.com/huggingface/lerobot/blob/v0.3.3/src/lerobot/datasets/lerobot_dataset.py). Public v2.0 and v2.1 compatibility reports are included in the [0.4.0 verification](../release-0.4.0.md).

## Not supported

- LeRobot v1 or an unrecognized v2 minor version
- Implicit network access for local paths; Hub downloads require an explicit Hub source
- Image-directory features for the video rule set
- Arbitrary custom video codecs unavailable to the installed OpenCV build
- Safety, calibration, or coordinate-frame conclusions not expressed by a configured rule

An absent capability produces `not_run`. A malformed metadata or source file produces a dataset or isolated rule error and never a clean pass.
