import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(
    os.environ.get("RUN_CAB_SMOKE") != "1",
    reason="Set RUN_CAB_SMOKE=1 to run live CAB smoke test.",
)
def test_live_cab_smoke(tmp_path: Path) -> None:
    out_path = tmp_path / "courses.json"
    checkpoint_path = tmp_path / "checkpoint.json"
    summary_path = tmp_path / "summary.json"

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "etl.scrape_cab",
            "--out",
            str(out_path),
            "--checkpoint",
            str(checkpoint_path),
            "--summary",
            str(summary_path),
            "--max-courses",
            "5",
            "--workers",
            "2",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    with out_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    assert isinstance(data, list)
    if data:
        assert "meetings" in data[0]
        assert isinstance(data[0]["meetings"], list)

