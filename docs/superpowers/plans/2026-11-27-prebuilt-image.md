# Prebuilt Image Implementation Plan

> **Correction made at the release.** The plan assumed the image tag keeps
> the git tag's `v` (`v0.1.1`, via `pattern=v{{version}}`). `metadata-action`
> strips a leading `v` from the pattern's result regardless — a scratch tag
> (`v0.1.0-test`) published as `0.1.0-test` — so the image tag is `0.1.1`,
> the guard compares the *published* version to `project.version`, and every
> doc pins `0.1.1`. Git tags keep the `v`.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An operator with Docker and a BirdNET-Go can install Birdhouse from a published `ghcr.io/danhon/birdhouse` image with no clone and no build.

**Architecture:** A tag-triggered GitHub Actions workflow tests, checks the tag against `pyproject.toml`, and pushes a `linux/amd64` image with the commit recorded (IMG-3). A second compose file runs that image with the same mounts, healthcheck and volumes as the source build, and a test compares the two files so they can't drift. INSTALL and RELEASING grow the new path without touching the old one.

**Tech Stack:** GitHub Actions (`docker/build-push-action`, `docker/metadata-action`), Docker Compose v2, GHCR, pytest.

**Spec:** `docs/superpowers/specs/2026-11-27-prebuilt-image-design.md`

## Global Constraints

- `linux/amd64` only. No arm64, no multi-arch (Dan, 2026-11-27).
- Registry `ghcr.io/danhon/birdhouse`; tags keep the leading `v` (`v0.1.1`), plus `latest` for a release only, never for a pre-release tag such as `v0.2.0-rc1`.
- The image records its commit: Dockerfile `GIT_SHA` build arg = `${{ github.sha }}`; `/healthz` reports it as `build` (IMG-3).
- No stored secrets: `packages: write` on `${{ github.token }}`, and only in the job that pushes.
- The reference deployment keeps building from source; `compose.yml` and `compose.override.yml` keep their behaviour, so `make deploy` and `make run` are untouched.
- The image compose keeps: the two required `${…:?}` host-path mounts read-only, `birdhouse-images:/app/data/image-cache`, `${BIRDHOUSE_LOG_DIR:-./logs}:/logs`, the `healthcheck.py` probe, `restart: unless-stopped`, and bounded `json-file` logging.
- On ubuntuplex, a `docker build` or a test suite runs through `~/dev/reverse-proxy/scripts/box-gate -- <cmd>` (MEM-3); it adds `nice -n 19` itself.
- Every commit ends with `Host: ubuntuplex` (DEV-6). Reviews at DEV-7 `medium` (a compose file changes).

## Review Focus

- A tag that doesn't match `project.version` — a person expects the image to be what the tag says; the workflow must fail before pushing, not after.
- A re-pushed tag — a person expects a published version to be immutable; the workflow must refuse an existing version rather than overwrite it and move `latest`.
- `BIRDHOUSE_IMAGE_TAG` unset or empty — a person expects the documented command to work; the compose must fall back to `latest`.
- A pre-release tag (`v0.2.0-rc1`) — a person expects `latest` to stay on the last real release.
- A compose edit landing in one file only, including the port mapping and `host.docker.internal` alias — a person expects the image install to behave like `make run`; the parity test must fail.
- No Docker CLI, or no Compose plugin, on the machine running `make test` — a person expects the suite to run; the parity test skips with a reason.

---

### Task 1: The release workflow

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `.github/workflows/tests.yml:8-12` (add `branches: ["**"]` to `push:`, keeping the other triggers)

**Interfaces:**
- Consumes: `pyproject.toml` `project.version`; the Dockerfile's `GIT_SHA` arg; `make test`.
- Produces: image `ghcr.io/danhon/birdhouse`, tagged `vX.Y.Z` (+ `latest` for a release only), `linux/amd64`, single manifest with no attestation index, labelled `org.opencontainers.image.revision` = the tagged commit. Task 4 relies on those tag names and that label.

- [ ] **Step 1: Write the workflow**

`.github/workflows/release.yml`:

```yaml
# A release is a tag: v0.1.1 tests, then builds and publishes the image for
# linux/amd64. The image-based install is INSTALL.md's quick start; the
# from-source path (make run) and the reference deployment (make deploy) are
# unchanged.
name: release

on:
  push:
    tags: ["v*"]

permissions:
  contents: read

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

jobs:
  test:
    runs-on: ubuntu-latest
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
        with:
          python-version: "3.12"
      - run: uv sync --frozen --extra dev
      - run: make test

  publish:
    needs: test
    runs-on: ubuntu-latest
    timeout-minutes: 20
    # ${{ github.token }} pushes to ghcr.io; no secret is stored. Only this
    # job may write, and only this job needs it.
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4

      # The tag is the version: refuse v0.1.1 over a pyproject that says
      # something else, before anything is pushed.
      - name: The tag matches project.version
        run: |
          version=$(python3 -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
          if [ "${GITHUB_REF_NAME#v}" != "$version" ]; then
            echo "tag ${GITHUB_REF_NAME} does not match project.version $version" >&2
            exit 1
          fi

      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ github.token }}

      # A published version never moves: a re-pushed tag fails here instead
      # of overwriting the image and re-pointing latest at it. Authenticated,
      # so first-release "not found" is trustworthy.
      - name: The version isn't published yet
        run: |
          if docker buildx imagetools inspect \
              "ghcr.io/danhon/birdhouse:${GITHUB_REF_NAME}" >/dev/null 2>&1; then
            echo "ghcr.io/danhon/birdhouse:${GITHUB_REF_NAME} already exists" >&2
            exit 1
          fi

      # v0.1.1 always; `latest` for a release only, never for a pre-release
      # tag such as v0.2.0-rc1 (the action's default flavour).
      - id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/danhon/birdhouse
          tags: |
            type=semver,pattern=v{{version}}

      - uses: docker/build-push-action@v6
        with:
          context: .
          platforms: linux/amd64
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}   # includes revision=${{ github.sha }}
          # One plain linux/amd64 manifest: the default attestation would
          # make the tag an index, so a pull's digest isn't the image's.
          provenance: false
          build-args: |
            GIT_SHA=${{ github.sha }}
          cache-from: type=gha,scope=release
          cache-to: type=gha,mode=max,scope=release
```

- [ ] **Step 2: Keep the test suite off tag pushes**

In `.github/workflows/tests.yml`, add `branches: ["**"]` to `push:` and leave the rest as it is, so the suite runs once per tag (inside `release.yml`) and PR CI is untouched:

```yaml
on:
  push:
    branches: ["**"]
    paths-ignore: ["**.md"]
  pull_request:
    paths-ignore: ["**.md"]
  workflow_dispatch:
```

- [ ] **Step 3: Check the workflow parses and is actionlint-clean**

Run: `uv run --with pyyaml python -c "import yaml; [yaml.safe_load(open(p)) for p in ('.github/workflows/release.yml','.github/workflows/tests.yml')]; print('ok')"`
Expected: `ok`

Then, if `actionlint` is available (`command -v actionlint`), run it on both files; unknown action inputs are exactly the failure mode this step is for.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml .github/workflows/tests.yml
git commit -m "Release: a tag publishes the image for linux/amd64

The workflow runs make test, refuses a tag that disagrees with
project.version, refuses a version already published, then pushes
ghcr.io/danhon/birdhouse: vX.Y.Z always and latest for a release only,
recording the commit in the image and its OCI labels. The test suite no
longer runs twice on a tag.

Host: ubuntuplex"
```

---

### Task 2: The image compose, and the test that keeps it honest

**Files:**
- Create: `compose.image.yml`
- Create: `tests/test_distribution.py`
- Modify: `compose.yml:1` (a header comment above `services:`)

**Interfaces:**
- Consumes: `compose.yml` + `compose.override.yml` as the reference for ports, `extra_hosts`, volumes, healthcheck, logging, `env_file` and `restart`.
- Produces: `compose.image.yml`, whose `app` service is the documented install; `tests/test_distribution.py` with `test_image_compose_matches_source_compose` and `test_image_compose_takes_a_pinned_version`.

- [ ] **Step 1: Write the failing test**

`tests/test_distribution.py`:

```python
"""The published image's compose file is the source build's, minus the build.

Two files that mount the same data can drift; this compares what Docker
Compose resolves for each, so an edit to one that isn't made to the other
fails here. Each file is resolved in its own throwaway directory with a stub
`.env`, because a clone has none and `env_file: .env` is required — and with
COMPOSE_* variables stripped, because `make deploy`/`make run` export them.

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
        command + ["config", "--format", "json"],
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
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run --extra dev pytest tests/test_distribution.py -q`
Expected: FAIL — `docker compose` reports no such file `compose.image.yml` (or the copy step raises)

- [ ] **Step 3: Write `compose.image.yml`**

The service body is `compose.yml`'s with the image in place of the build, plus `compose.override.yml`'s port and `host.docker.internal` alias:

```yaml
# Installing from the published image: INSTALL.md's quick start. One file,
# one command, no clone and no build:
#   docker compose -f compose.image.yml up -d
# linux/amd64 only. Pin a version with BIRDHOUSE_IMAGE_TAG=v0.1.1; the
# default is latest. The source build (compose.yml + compose.override.yml,
# `make run`) and a deployment (`make deploy`) are unchanged.
services:
  app:
    image: ghcr.io/danhon/birdhouse:${BIRDHOUSE_IMAGE_TAG:-latest}
    env_file: .env
    restart: unless-stopped
    ports:
      - "127.0.0.1:8090:8090"
    extra_hosts:
      - "host.docker.internal:host-gateway"
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    healthcheck:
      test: ["CMD", "python3", "-I", "-S", "/app/src/birdhouse/healthcheck.py"]
      interval: 30s
      timeout: 3s
      retries: 3
      start_period: 60s
      start_interval: 1s
    volumes:
      - ${BIRDNET_DB_HOST_PATH:?set BIRDNET_DB_HOST_PATH in .env}:/data/birdnet.db:ro
      - ${BIRDNET_TAXONOMY_HOST_PATH:?set BIRDNET_TAXONOMY_HOST_PATH in .env}:/data/taxonomy.csv:ro
      - birdhouse-images:/app/data/image-cache
      - ${BIRDHOUSE_LOG_DIR:-./logs}:/logs

volumes:
  birdhouse-images:
```

- [ ] **Step 4: Run the test again**

Run: `uv run --extra dev pytest tests/test_distribution.py -q`
Expected: `2 passed` (or `2 skipped` where there is no Compose CLI)

- [ ] **Step 5: Point `compose.yml` at its sibling**

Insert a header comment **above** the existing `services:` line (don't replace it):

```yaml
# The source build: `make run`, or a deployment that sets COMPOSE_FILE.
# Installing from the published image instead: compose.image.yml.
services:
```

- [ ] **Step 6: Run the whole suite through the box gate**

Run: `~/dev/reverse-proxy/scripts/box-gate -- make test`
Expected: PASS, with `test_distribution.py`'s two tests passed or skipped

- [ ] **Step 7: Commit**

```bash
git add compose.image.yml compose.yml tests/test_distribution.py
git commit -m "Image install: compose.image.yml, and a test against drift

The published image runs the same service as the source build — the two
BirdNET-Go mounts, the photo-cache volume, the logs, the healthcheck and
bounded logging — with the port and host.docker.internal alias that
compose.override.yml carries for make run. A pytest compares what Docker
Compose resolves for both and skips where there is no Compose CLI.

Host: ubuntuplex"
```

---

### Task 3: The documented install

**Files:**
- Modify: `INSTALL.md` (a *Quick start* section before *Configure*; a lead-in for the from-source sections; an *Upgrades* bullet; a *Configuration* row)
- Modify: `README.md:35-49` (the quick start block)
- Modify: `RELEASING.md` (the "no Docker CI" sentence; a new *The image* section with the after-the-tag steps)

**Interfaces:**
- Consumes: `compose.image.yml` and its `BIRDHOUSE_IMAGE_TAG` variable (Task 2); the tags `ghcr.io/danhon/birdhouse:vX.Y.Z` and `latest` (Task 1).
- Produces: the words Task 4's verification reads, and the release checklist the next tag follows.

- [ ] **Step 1: Write INSTALL.md's quick start**

Insert before `## Configure`:

````markdown
## Quick start (the published image)

Birdhouse publishes an image for **linux/amd64**. Nothing is built: two
files, one command. You still need the two BirdNET-Go files from
[Before you start](#before-you-start).

```bash
mkdir birdhouse && cd birdhouse
curl -fsSLO https://raw.githubusercontent.com/danhon/Birdhouse/main/compose.image.yml
curl -fsSL https://raw.githubusercontent.com/danhon/Birdhouse/main/.env.example -o .env
$EDITOR .env            # the two BirdNET-Go host paths
mkdir -p logs
docker compose -f compose.image.yml up -d
# then open http://127.0.0.1:8090
```

The image is `ghcr.io/danhon/birdhouse:latest` by default. To pin a version,
add `BIRDHOUSE_IMAGE_TAG=v0.1.1` to `.env` or before the command.

If BirdNET-Go runs on this machine, also set
`BIRDNET_BASE_URL=http://host.docker.internal:8080` in `.env` — the compose
file provides that hostname — or common names fall back to iNaturalist.

Everything after this applies to either install: the same configuration,
the same preflight and diagnostics, and the same public-page warning. The
sections below **build from source**; skip to
[When the page says it can't read BirdNET-Go](#when-the-page-says-it-cant-read-birdnet-go)
if you used the image.
````

- [ ] **Step 2: Add the image to README's quick start**

Replace `README.md:35-49` (the `## Quick start` block) so both paths are named:

````markdown
## Quick start

From the published image — no clone, no build (linux/amd64):

```bash
mkdir birdhouse && cd birdhouse
curl -fsSLO https://raw.githubusercontent.com/danhon/Birdhouse/main/compose.image.yml
curl -fsSL https://raw.githubusercontent.com/danhon/Birdhouse/main/.env.example -o .env
$EDITOR .env          # the two BirdNET-Go host paths
mkdir -p logs
docker compose -f compose.image.yml up -d
```

Or from source:

```bash
git clone https://github.com/danhon/Birdhouse.git
cd Birdhouse
cp .env.example .env
$EDITOR .env          # the two BirdNET-Go host paths
make run              # docker compose, http://127.0.0.1:8090
```
````

- [ ] **Step 3: Add the upgrade line and the configuration row to INSTALL.md**

In *Upgrades, the cache and backups*, before the existing bullet about pulling a commit:

```markdown
- **Image install:** `docker compose -f compose.image.yml pull`, then
  `up -d` again; change `BIRDHOUSE_IMAGE_TAG` to move to another version.
  The photo cache volume persists, but it is named after the folder you run
  in — moving from a `make run` install to the image re-fetches photos once.
```

In the *Configuration* table, one row:

```markdown
| `BIRDHOUSE_IMAGE_TAG` | `latest` | Image install only: the version to run |
```

- [ ] **Step 4: Fix and extend RELEASING.md**

Replace the opening claim that there is no Docker CI:

```markdown
There is no browser CI: the test suite guards the code, a `release` workflow
builds and publishes the image from a tag, and a release is still gated by
one fresh install that follows the stranger's path. Do the checklist below
before a tag, and record the result.
```

Then, after the checklist and before `## The v0.1.0 run`, add:

````markdown
## The image

A release tag publishes `ghcr.io/danhon/birdhouse:<version>` and `latest`
for `linux/amd64`, built by `.github/workflows/release.yml`. The workflow
refuses a tag whose number doesn't match `project.version`, so bump
`pyproject.toml` and `CHANGELOG.md` *before* tagging — character for
character, so a pre-release is `0.2.0-rc1` in both, not `0.2.0rc1`.

After the tag:

- [ ] The tag's `release` workflow is green, and the run lists the version
      tag and (for a release) `latest`.
- [ ] The package is public — a first release only. A GHCR package pushed by
      `GITHUB_TOKEN` starts private; change its visibility at
      <https://github.com/users/danhon/packages/container/birdhouse/settings>.
- [ ] `docker pull ghcr.io/danhon/birdhouse:vX.Y.Z` works **without**
      credentials, from a shell with no `docker login`.
- [ ] `/healthz` in that image reports the tagged commit
      (`curl -s localhost:8090/healthz` → `"build":"<sha>"`).

The image-based install is `compose.image.yml` (INSTALL.md, *Quick start*).
The reference deployment still builds from source with `make deploy`.
````

- [ ] **Step 5: Read the instructions back**

Run: `grep -n "Quick start\|compose.image.yml\|BIRDHOUSE_IMAGE_TAG" INSTALL.md README.md RELEASING.md`
Expected: each file names the file and the variable; no heading appears twice; the "or build" pointer sits inside the quick start, not as an empty `###` heading.

- [ ] **Step 6: Commit**

```bash
git add INSTALL.md README.md RELEASING.md
git commit -m "Docs: install from the published image

INSTALL's quick start downloads compose.image.yml and .env.example and runs
one command, with version pinning and upgrades; the source path stays. The
release notes gain the tag, the image, the one-time visibility change and an
anonymous pull.

Host: ubuntuplex"
```

---

### Task 4: Prove it, then cut v0.1.1

**Files:**
- Modify: `pyproject.toml:3` (`version = "0.1.1"`)
- Modify: `CHANGELOG.md` (a `## v0.1.1` section)
- Modify: `RELEASING.md` (a record of the run, as v0.1.0's)

**Interfaces:**
- Consumes: everything above.
- Produces: a public `ghcr.io/danhon/birdhouse:v0.1.1` whose `/healthz` names the release commit, and a recorded check.

- [ ] **Step 1: Prove the workflow's image locally, before any tag**

Through the box gate, build the same Dockerfile the workflow builds:

```bash
~/dev/reverse-proxy/scripts/box-gate -- docker build --platform linux/amd64 \
  -t ghcr.io/danhon/birdhouse:latest -t ghcr.io/danhon/birdhouse:v0.1.1 \
  --build-arg GIT_SHA=$(git rev-parse HEAD) .
```

Then, in a throwaway folder outside the checkout, copy `compose.image.yml`
and a `.env` naming this box's BirdNET-Go paths **without** a clone, and run
`docker compose -f compose.image.yml up -d` under
`COMPOSE_PROJECT_NAME=birdhouse-image-check`. Walk the RELEASING checklist
(slide credit, species list, history bars and calendar, ← / →, the
diagnostic). Remove the project, its volume and the local image afterwards.

- [ ] **Step 2: Bump the version and write the changelog**

`pyproject.toml`: `version = "0.1.1"`. `CHANGELOG.md`, above v0.1.0:

```markdown
## v0.1.1 — 2026-11-27

- Birdhouse is published as an image, `ghcr.io/danhon/birdhouse` for
  linux/amd64: install with `compose.image.yml` and no build, pinning a
  version with `BIRDHOUSE_IMAGE_TAG`. The source install is unchanged.
```

The `Birhouse/0.1` User-Agent in `start_background_poller` names the project,
not the release; leave it.

- [ ] **Step 3: Commit, run the suite, push main**

```bash
~/dev/reverse-proxy/scripts/box-gate -- make test
git add pyproject.toml CHANGELOG.md
git commit -m "v0.1.1: the image install

Host: ubuntuplex"
git push origin main && ci-wait
```

Expected: the suite passes; `ci-wait` reports the tests workflow green.

- [ ] **Step 4: Prove the tag guard before trusting it**

```bash
git tag v0.1.0-test && git push origin v0.1.0-test
ci-wait release          # expect a failure at "The tag matches project.version"
git push --delete origin v0.1.0-test && git tag -d v0.1.0-test
```

Expected: the run stops at the version check, and the registry has no
`v0.1.0-test` tag.

- [ ] **Step 5: Tag and push, then watch the release**

```bash
git tag -a v0.1.1 -m "v0.1.1: the image install"
git push origin v0.1.1 && ci-wait release
```

Expected: the `release` workflow's `test` and `publish` jobs green; the run
page lists `v0.1.1` and `latest`.

- [ ] **Step 6: Make the package public (Dan, once)**

Change visibility at
<https://github.com/users/danhon/packages/container/birdhouse/settings>, then
with no Docker login in the environment:

```bash
docker logout ghcr.io || true
docker pull ghcr.io/danhon/birdhouse:v0.1.1
```

Expected: the pull succeeds with no credentials.

- [ ] **Step 7: Check the published image's commit**

```bash
docker run --rm -d --name birdhouse-sha -e PORT=8090 -p 127.0.0.1:8091:8090 \
  ghcr.io/danhon/birdhouse:v0.1.1
sleep 5; curl -s http://127.0.0.1:8091/healthz; docker rm -f birdhouse-sha
```

Expected: `build` is the full SHA that v0.1.1 tags
(`git rev-parse v0.1.1^{commit}`), not `dev`.

- [ ] **Step 8: Record the run in RELEASING.md, commit, push**

Add `## The v0.1.1 run — 2026-11-27` with the checklist results, the run
URL and the pulled digest. Then:

```bash
git add RELEASING.md
git commit -m "Record the v0.1.1 image run

Host: ubuntuplex"
git push origin main && ci-wait
```

Expected: CI green. (`make docs-verify` is reverse-proxy's; this repo
publishes nothing to the docs site.)
