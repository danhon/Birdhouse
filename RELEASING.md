# Releasing Birdhouse

There is no browser CI: the test suite guards the code, a `release` workflow
builds and publishes the image from a tag, and a release is still gated by
one fresh install that follows the stranger's path. Two lists follow: the
**Checklist** is done *before* the tag, and **The image** has a *before* and
an *after* part. Record the result below.

## Checklist

- [ ] `make test` passes (lint, template parse, pytest).
- [ ] CI on `main` is green.
- [ ] Clone the public repository into an empty folder outside this checkout.
- [ ] `cp .env.example .env`; set the two BirdNET-Go host paths (a real
      BirdNET-Go's `birdnet.db` and `taxonomy.csv`).
- [ ] `make run` builds and serves `http://127.0.0.1:8090`.
- [ ] The page shows a slide with a photograph and a **photo credit**.
- [ ] **N species today** opens the list.
- [ ] Tapping a **common name** opens a last-30-days panel; Bars and Calendar
      both render, and the switch flips them.
- [ ] ← / → step the bird and its history together.
- [ ] The diagnostic page is exercised: point `BIRDNET_DB_HOST_PATH` at a
      missing file, confirm the page names it, then restore it (recreating the
      container if the mount changed) and confirm the carousel returns.
- [ ] Stop and remove the check's compose project and photo volume.

## The image

A release tag publishes `ghcr.io/danhon/birdhouse:<version without its v>`
and `latest`
for `linux/amd64`, built by `.github/workflows/release.yml`. The workflow
refuses a tag whose number doesn't match `project.version`, so bump
`pyproject.toml` and `CHANGELOG.md` *before* tagging — character for
character, so a pre-release is `0.2.0-rc1` in both, not `0.2.0rc1`.

Before the tag:

- [ ] `pyproject.toml` and `uv.lock` agree: bump `version`, run `uv lock`,
      and commit `uv.lock` with the bump. A stale lock makes `make test`
      rewrite it, leaving a dirty checkout that `make deploy` refuses.
- [ ] `actionlint` passes on `.github/workflows/release.yml` and
      `tests.yml` (an unknown action input only fails on a tag push
      otherwise).
- [ ] Build the image and run it through the install file the stranger gets:
      `docker build --build-arg GIT_SHA=$(git rev-parse --short HEAD) -t ghcr.io/danhon/birdhouse:local .`,
      then, in an empty folder, do what the quick start does: copy
      `compose.image.yml` and your real `.env` in, `mkdir -p logs`, and run
      `COMPOSE_PROJECT_NAME=birdhouse-image-check BIRDHOUSE_IMAGE_TAG=local docker compose -f compose.image.yml up -d`
      *there*. (Compose takes the folder of the `-f` file as the project
      directory, so pointing `-f` at the checkout would read the checkout's
      `.env`, `logs` and volume.) The page serves, and `/healthz` reports
      that commit. Afterwards
      `COMPOSE_PROJECT_NAME=birdhouse-image-check docker compose -f compose.image.yml down -v`,
      remove the folder, and `docker rmi ghcr.io/danhon/birdhouse:local`.
      **Always set `COMPOSE_PROJECT_NAME=birdhouse-image-check`** on every
      Compose command of these checks: a folder named `birdhouse` makes
      Compose's project `birdhouse`, which is the live deployment's — `up -d`
      would recreate its container without its Traefik overlay, and `down -v`
      would delete its photo cache, `.focus` crop anchors included.

After the tag:

- [ ] The tag's `release` workflow is green, and the run lists the version
      tag and (for a release) `latest`.
- [ ] The package is public — a first release only. A GHCR package pushed by
      `GITHUB_TOKEN` starts private; change its visibility at
      <https://github.com/users/danhon/packages/container/birdhouse/settings>.
- [ ] `docker pull ghcr.io/danhon/birdhouse:X.Y.Z` works **without**
      credentials, from a shell with no `docker login`.
- [ ] In an empty folder, run INSTALL.md's *Quick start* as written, with
      `COMPOSE_PROJECT_NAME=birdhouse-image-check` set in the environment
      of every `docker compose` command (the quick start's `mkdir birdhouse`
      would otherwise name the project after the live deployment's; see
      above) and `BIRDHOUSE_IMAGE_TAG=X.Y.Z` in `.env` (the image tag drops the git tag's
      `v`): it pulls, the
      three-point check in *Run* passes, and `/healthz` reports the tagged
      commit (`curl -s localhost:8090/healthz` → `"build":"<sha>"`). Remove
      that check's project and volume afterwards with
      `COMPOSE_PROJECT_NAME=birdhouse-image-check docker compose -f compose.image.yml down -v`.
- [ ] On the first release only, and only now that the pull above works
      without credentials, delete the "No image is published yet" paragraph
      from INSTALL.md's *Quick start* **and** the matching line above the
      image block in README.md's *Quick start*.

**A failed release.** If the run fails before anything is pushed to the
registry (the version check, a missing image, `actionlint`'s kind of
mistake), fix it, then delete and re-push the tag — nothing published has
moved. Once any image has been pushed, **never re-push a tag**: the
workflow refuses an existing version on purpose. Bump the version instead.

If GHCR words a missing tag differently from `not found`, `manifest
unknown` or `name unknown`, the first release stops at that check with the
output printed. That is safe; add the wording to the pattern in
`release.yml` and re-run.

The image-based install is `compose.image.yml` (INSTALL.md, *Quick start*).
The reference deployment still builds from source with `make deploy`.

## The v0.1.0 run — 2026-11-27

Run from a fresh `git clone` of `danhon/Birdhouse` at `1c7d944` into
`~/birdhouse-install-check`, with the host paths from the reference box.
The same compose files and environment as `make run`, started detached so the
checklist could inspect it.

- [x] `make test`: 147 passed (lint, template parse, pytest).
- [x] CI on `main`: [run 46089229864](https://github.com/danhon/Birdhouse/actions/runs/46089229864), green.
- [x] Fresh clone; `.env` from `.env.example` with the two BirdNET-Go paths.
- [x] Built and served `http://127.0.0.1:8090`; healthy in 13 s, 77 species
      after 20 s.
- [x] Slide showed a photograph and its credit; the credits included
      `Photo: samzhang` and `Photo: Judy Gallagher · CC BY`.
- [x] **77 species today** opened the list.
- [x] A common name opened the last-30-days panel: 30 bars, the calendar
      rendered 12 present days, the Bars · Calendar switch flipped it, and
      ← / → moved from Sandhill Crane (0) to White-throated Sparrow (1).
      Escape closed the panel.
- [x] Diagnostic: with `BIRDNET_DB_HOST_PATH` set to a missing path, the page
      said "The display can't read BirdNET-Go" and "could not be read"
      (Docker creates a directory for a missing bind source). Restoring the
      path and recreating the container brought the carousel back in ~5 s.
      A changed mount needs the container recreated; the page itself retries
      every minute.
- [x] The check's compose project and photo volume were removed, as was the
      clone.

Not exercised: the BirdNET-Go API at `BIRDNET_BASE_URL` is unreachable from
that detached local stack, so common names came from iNaturalist — which is
the documented fallback. A real deployment with the API reachable needs one
morning of real data to confirm the same page.
