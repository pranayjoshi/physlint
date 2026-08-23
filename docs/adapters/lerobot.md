# LeRobot adapter

Physlint `0.1.x` recognizes a local directory as LeRobot when `meta/info.json` declares `features`, `fps`, and a `codebase_version` beginning with `v3`.

## Supported

- v3.x `info.json` feature and path templates
- Chunked Parquet episode metadata under `meta/episodes/`
- Multiple episodes sharing a Parquet file, filtered lazily by `episode_index`
- Fixed-size and regular variable-list numeric features
- Shared MP4 files segmented using per-camera episode timestamp ranges
- Metadata-first inventory without decoding video

## Not supported

- LeRobot v2.0/v2.1; migrate it with the official LeRobot converter
- Remote Hugging Face Hub identifiers or implicit downloads
- Image-directory features for the video rule set
- Arbitrary custom video codecs unavailable to the installed OpenCV build
- Safety, calibration, or coordinate-frame conclusions not expressed by a configured rule

An absent capability produces `not_run`. A malformed metadata or source file produces a dataset or isolated rule error and never a clean pass.
