#!/usr/bin/env python3
"""Parse the rendered page's inline JavaScript: `make check-template`.

The carousel, overlays and history charts are inline JS in index.html, and
the pytest suite never parses them. This renders the page with made-up
species through Flask's test client and runs `node --check` on the script,
so a typo is a failed check rather than a silent wall.
"""

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from zoneinfo import ZoneInfo

from birdhouse.app import Config, Species, create_app, _store


def main() -> int:
    node = shutil.which("node")
    if node is None:
        print("check-template: node is required (https://nodejs.org)", file=sys.stderr)
        return 1

    config = Config(
        birdnet_base_url="http://localhost",
        birdnet_db_path=Path("unused.db"),
        port=8090,
        image_cache_dir=Path(tempfile.gettempdir()) / "birdhouse-check-images",
        min_confidence=0.6,
        timezone=ZoneInfo("America/Los_Angeles"),
        poll_interval=60,
        slide_duration=8,
        vision_enabled=False,
    )
    _store.update(
        [Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3),
         Species("Great Horned Owl", "Bubo virginianus", "9:00 pm", 1)],
        "Friday 27 November 2026", "4:40 pm",
    )
    html = create_app(config).test_client().get("/").data.decode()
    _store.update([], "", "")

    match = re.search(r"<script>(.*?)</script>", html, re.S)
    if match is None:
        print("check-template: the rendered page has no inline script", file=sys.stderr)
        return 1

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(match.group(1))
        path = f.name
    try:
        result = subprocess.run([node, "--check", path])
    finally:
        Path(path).unlink(missing_ok=True)
    if result.returncode == 0:
        print("check-template: the inline JavaScript parses")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
