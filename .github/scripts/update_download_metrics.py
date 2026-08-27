"""Refresh the Shields-compatible PyPI download badge snapshot."""

from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_URL = "https://pypistats.org/api/packages/physlint/recent?period=month"


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: update_download_metrics.py OUTPUT")

    output = Path(sys.argv[1])
    request = Request(API_URL, headers={"User-Agent": "physlint-download-metrics/1.0"})
    payload: dict[str, object] | None = None

    for attempt in range(4):
        try:
            with urlopen(request, timeout=30) as response:  # noqa: S310
                payload = json.load(response)
            break
        except (HTTPError, URLError, TimeoutError) as error:
            if attempt == 3:
                print(f"::warning::PyPI Stats unavailable; keeping the previous snapshot: {error}")
                return 0
            time.sleep(2**attempt * 5)

    if payload is None:
        return 0
    data = payload.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("last_month"), int):
        print("::warning::PyPI Stats returned an unexpected response; keeping the previous snapshot")
        return 0

    downloads = data["last_month"]
    snapshot = {
        "schemaVersion": 1,
        "label": "downloads/month",
        "message": f"{downloads:,}",
        "color": "brightgreen" if downloads else "lightgrey",
        "cacheSeconds": 86400,
        "updated_at": datetime.now(UTC).isoformat(),
        "source": API_URL,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Updated monthly download snapshot: {downloads:,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
