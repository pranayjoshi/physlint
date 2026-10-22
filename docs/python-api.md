# Python API

Physlint's public Python API returns typed Pydantic models and does not render terminal output.

```python
from physlint import check_dataset, inspect_dataset

inventory = inspect_dataset("/data/recording.mcap", profile="ros2")
report = check_dataset("/data/recording.mcap")

if report.status == "failed":
    for result in report.results:
        for finding in result.findings:
            print(finding.rule_id, finding.message)
```

Revision-pinned Hugging Face datasets require the `hub` extra:

```python
report = check_dataset(
    "hf://datasets/owner/dataset@REVISION",
    offline=False,
    cache_dir="/var/cache/huggingface",
)
```

Config-declared plugins are disabled by default in the public API. Enable them only for a trusted configuration:

```python
report = check_dataset(
    "/data/trusted-dataset",
    config_path="physlint.yaml",
    allow_config_plugins=True,
)
```

The returned models expose `model_dump()`, `model_dump_json()`, and `model_json_schema()` through Pydantic. New fields may be added compatibly within report schema `1.x`; consumers should reject unsupported major schema versions.
