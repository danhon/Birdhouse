"""The published image's compose file is the source build's, minus the build.

Two files that mount the same data can drift; this compares what Docker
Compose resolves for each, so an edit to one that isn't made to the other
fails here. Both are resolved in the same throwaway directory, so relative
paths and volume names resolve alike, with a stub `.env`, because a clone has none and `env_file: .env` is required — and with
COMPOSE_* variables stripped, because `make deploy`/`make run` export them.
`--no-env-resolution` keeps `env_file` in the output; without it Compose folds
the file's contents into `environment` and the `env_file` key disappears.

The whole resolved service (less `build` and `image`) and the project's
`volumes:` are compared, so a key added to one file and not the other fails
here with the precise difference.

Skipped where there is no Docker, no Compose plugin, or a Compose without
`--no-env-resolution`, so `make test` still runs on such a machine.
"""

import functools
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


@functools.cache
def _skip_reason() -> str:
    if shutil.which("docker") is None:
        return "docker not installed"
    if subprocess.run(["docker", "compose", "version"], capture_output=True).returncode:
        return "docker compose CLI not installed"
    help_text = subprocess.run(
        ["docker", "compose", "config", "--help"], capture_output=True, text=True
    )
    if "--no-env-resolution" not in help_text.stdout + help_text.stderr:
        return "this docker compose has no `config --no-env-resolution`"
    return ""


def _resolved(tmp_path: Path, *compose_files: str, **extra: str) -> dict:
    """The whole resolved project, as `docker compose config` prints it."""
    if reason := _skip_reason():
        pytest.skip(reason)
    for name in compose_files:
        shutil.copy(ROOT / name, tmp_path / name)
    (tmp_path / ".env").write_text("")
    env = {
        k: v
        for k, v in os.environ.items()
        if not k.startswith("COMPOSE_") and k != "BIRDHOUSE_LOG_DIR"
    }
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
    return json.loads(proc.stdout)


def test_image_compose_matches_source_compose(tmp_path):
    source = _resolved(tmp_path, "compose.yml", "compose.override.yml")
    image = _resolved(tmp_path, "compose.image.yml", BIRDHOUSE_IMAGE_TAG="")
    source_app = source["services"]["app"]
    image_app = image["services"]["app"]

    assert "build" not in image_app, "the image install must not build"
    assert image_app["image"] == "ghcr.io/danhon/birdhouse:latest"

    def without_build_and_image(service: dict) -> dict:
        return {k: v for k, v in service.items() if k not in ("build", "image")}

    assert without_build_and_image(image_app) == without_build_and_image(source_app)
    assert image["volumes"] == source["volumes"]


def test_image_compose_takes_a_pinned_version(tmp_path):
    image = _resolved(tmp_path, "compose.image.yml", BIRDHOUSE_IMAGE_TAG="v0.1.1")
    assert image["services"]["app"]["image"] == "ghcr.io/danhon/birdhouse:v0.1.1"
