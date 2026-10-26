from __future__ import annotations

import hashlib
import json
from pathlib import Path

from physlint import __version__

ROOT = Path(__file__).resolve().parents[1] / "validation/reports/release-0.4.0"


def test_current_release_reports_are_complete_and_sanitized():
    hashes = json.loads((ROOT / "checksums.json").read_text())
    assert len(hashes) >= 16
    for name, digest in hashes.items():
        content = (ROOT / name).read_bytes()
        assert hashlib.sha256(content).hexdigest() == digest
        assert b"/Users/" not in content and b"/private/" not in content and b"/home/" not in content
        report = json.loads(content)
        assert report["physlint_version"] == __version__
    v3 = json.loads((ROOT / "lerobot-v3/summary.json").read_text())
    assert v3["clean_passed"] == 4
    assert v3["controlled_corruptions_detected"] == 3
    mcap = json.loads((ROOT / "mcap/summary.json").read_text())
    assert mcap["expected_outcomes_verified"] == 4
    v2 = json.loads((ROOT / "lerobot-v2/summary.json").read_text())
    assert {item["format"] for item in v2["results"]} == {"v2.0", "v2.1"}
    assert all(item["status"] == "passed" and item["errored"] == 0 for item in v2["results"])
