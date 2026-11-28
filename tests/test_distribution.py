"""The published image's compose file is the source build's, minus the build.

Two files that mount the same data can drift; this compares what Docker
Compose resolves for each, so an edit to one that isn't made to the other
fails here. Each file is resolved in its own throwaway directory with a stub
`.env`, because a clone has none and `env_file: .env` is required — and with
COMPOSE_* variables stripped, because `make deploy`/`make run` export them.
`--no-env-resolution` keeps `env_file` in the output; without it Compose folds
the file's contents into `environment` and the `env_file` key disappears.

Skipped where there is no Compose CLI, so `make test` still runs on a machine
without Docker.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_ENV = {
    "BIRDNET_DB_HOST_PATH": "/tmp/birdnet.db",
    "BIRDNET_TAXONOMY_HOST_PATH": "/tmp/taxonomy.csv",
}


def _resolved(tmp_path: Path, *compose_files: str, **extra: str) -> dict:
    if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
        pytest.skip("docker compose CLI not installed")
    for name in compose_files:
        shutil.copy(ROOT / name, tmp_path / name)
    (tmp_path / ".env").write_text("")
    env = {k: v for k, v in os.environ.items() if not k.startswith("COMPOSE_")}
    env.update(REQUIRED_ENV, **extra)
    command = ["docker", "compose"]
    for name in compose_files:
        command += ["-f", name]
    proc = subprocess.run(
        command + ["config", "--no-env-resolution", "--format", "json"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)["services"]["app"]


def test_image_compose_matches_source_compose(tmp_path):
    source = _resolved(tmp_path, "compose.yml", "compose.override.yml")
    image = _resolved(tmp_path, "compose.image.yml", BIRDHOUSE_IMAGE_TAG="")

    assert "build" not in image, "the image install must not build"
    assert image["image"] == "ghcr.io/danhon/birdhouse:latest"

    for key in (
        "ports",
        "extra_hosts",
        "volumes",
        "healthcheck",
        "logging",
        "env_file",
        "restart",
    ):
        assert image[key] == source[key], f"{key} differs from `make run`'s compose"


def test_image_compose_takes_a_pinned_version(tmp_path):
    image = _resolved(tmp_path, "compose.image.yml", BIRDHOUSE_IMAGE_TAG="v0.1.1")
    assert image["image"] == "ghcr.io/danhon/birdhouse:v0.1.1"
