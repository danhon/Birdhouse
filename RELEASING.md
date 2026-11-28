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
- [ ] The package is public: an anonymous pull (below) is the test. For
      `v0.1.1` it came out public without a visibility change, the package
      inheriting the public repository; if a future package starts private,
      change it at
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
- [ ] If this release is the first with the image, and only once the pull
      above works without credentials, take any "not published yet" wording
      out of INSTALL.md's and README.md's *Quick start* (done at `v0.1.1`).

**A failed release.** If the run fails before anything is pushed to the
registry (the version check, a missing image, `actionlint`'s kind of
mistake), fix it, then delete and re-push the tag — nothing published has
moved. Once any image has been pushed, **never re-push a tag**: the
workflow refuses an existing version on purpose. Bump the version instead.

If GHCR words a missing tag differently from `not found`, `manifest
unknown` or `name unknown`, a release stops at that check with the output
printed. That is safe; add the wording to the pattern in `release.yml` and
re-run the tag (nothing was pushed).

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

## The v0.1.1 run — 2026-11-27

The first image release. Before the tag: [run 46111506985](https://github.com/danhon/Birdhouse/actions/runs/46111506985)
green; the image built locally from `319ba18` and served through
`compose.image.yml` in a throwaway folder as project
`birdhouse-image-check` — 79 species, photo credits, the 30-day history and
`/healthz` naming the commit. The live deployment (`birdhouse`, up 5 hours)
was untouched.

- [x] The tag/version guard was proved first with a scratch tag,
      `v0.1.0-test`: the `test` job passed and `publish` refused it at the
      version check ([run 46111545927](https://github.com/danhon/Birdhouse/actions/runs/46111545927)).
      That run also showed `metadata-action` publishes `0.1.0-test` from
      `v0.1.0-test` even with `pattern=v{{version}}`: image tags carry no
      `v`. The pattern, the guard and every doc were corrected before the
      real tag.
- [x] `make test` 149 passed (with `uv lock` refreshed for 0.1.1) and
      `actionlint` clean on both workflows.
- [x] `v0.1.1` at `cf64b5f` published by [run 46111687839](https://github.com/danhon/Birdhouse/actions/runs/46111687839):
      `ghcr.io/danhon/birdhouse:0.1.1` and `:latest`.
- [x] The package was public with no visibility change: `docker pull` with an
      empty `DOCKER_CONFIG` fetched `0.1.1` (`sha256:48343ad8a68f`) and
      `latest`.
- [x] `/healthz` from the pulled image reports `cf64b5f3791f0ad9cc8300e79f27af389f0f313f`,
      the tagged commit.
- [x] INSTALL's quick start from the pulled image, as project
      `birdhouse-image-check`: 79 species, a slide with a photo credit, the
      history panel, `/healthz` on the pulled tag. Project and volume
      removed afterwards.
- [x] The "not yet published" text came out of INSTALL.md and README.md in
      the same commit.

Not exercised: a pre-release tag's `latest` behaviour, and arm64 (refused
by design).
