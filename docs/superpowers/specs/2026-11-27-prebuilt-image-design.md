# Distribution: a published image (design)

> **Correction made at the release.** The plan assumed the image tag keeps
> the git tag's `v` (`v0.1.1`, via `pattern=v{{version}}`). `metadata-action`
> strips a leading `v` from the pattern's result regardless — a scratch tag
> (`v0.1.0-test`) published as `0.1.0-test` — so the image tag is `0.1.1`,
> the guard compares the *published* version to `project.version`, and every
> doc pins `0.1.1`. Git tags keep the `v`.

Issue: [danhon/Birdhouse#10](https://github.com/danhon/Birdhouse/issues/10).
Status: agreed with Dan 2026-11-27 — **linux/amd64 only**, no arm64 until
someone asks for it.

## What changes

v0.1.0 is source-only: an operator clones the repo, writes `.env`, and
`make run` builds the image on their machine. That is the last friction
between "I have BirdNET-Go" and "I have a wall". This adds one more install
path beside it, and changes nothing about the existing one.

Unchanged on purpose: SQLite as the only data path
([ADR 0001](../adr/0001-birdnet-go-sqlite-not-api.md)); no authentication
and the public-page warning; the two read-only BirdNET-Go mounts, the
required host-path variables, the photo-cache volume, port 8090 on
127.0.0.1, and the healthcheck. The reference deployment keeps building
from source with `make deploy`.

## The pieces

1. **A release workflow, `.github/workflows/release.yml`.** On a `v*` tag
   push: run `make test`, refuse a tag whose number doesn't match
   `pyproject.toml`'s `project.version`, refuse a version already
   published, then build and push `ghcr.io/danhon/birdhouse` for
   `linux/amd64` with
   - the tag's version, `v` kept (`v0.1.1`) — `metadata-action`'s semver
     pattern strips a leading `v` unless the pattern spells it in
     (`v{{version}}`),
   - `latest`, for releases only — a pre-release tag such as `v0.2.0-rc1`
     pushes no `latest`,
   - one plain manifest, not an index with an attestation, so a pull's
     digest is the image's (`provenance: false`),
   - OCI labels naming the source repository and the exact commit
     (`org.opencontainers.image.revision`),
   and the Dockerfile's own `GIT_SHA` build arg set to the same commit, so
   `/healthz` reports it (IMG-3).

   A published version never moves: a re-pushed tag fails at an
   authenticated `imagetools inspect` before anything is built, rather than
   overwriting the image and re-pointing `latest` at an old commit.

   `docker/metadata-action` produces the tags and labels, so a pre-release
   can't accidentally move `latest`; `docker/build-push-action` builds and
   pushes with the GitHub Actions cache. `packages: write` on
   `${{ github.token }}` is the whole credential: no secret is stored.

2. **`compose.image.yml`.** The same service as `compose.yml` with
   `image: ghcr.io/danhon/birdhouse:${BIRDHOUSE_IMAGE_TAG:-latest}` instead
   of `build:`, and the 127.0.0.1 port mapping and `host.docker.internal`
   alias that `compose.override.yml` carries for `make run`, folded in — so
   a quick start is one file and one command, with no clone.

3. **A parity test, `tests/test_distribution.py`.** Two compose files that
   mount the same paths can drift; the test runs
   `docker compose config --format json` on both (with the two required
   host paths in the environment) and asserts the image file's `volumes`,
   `healthcheck`, `logging`, `env_file` and `restart` equal the source
   file's, and that it has an `image` and no `build`. It skips when the
   `docker` CLI is absent, so the unit suite still runs anywhere `make test`
   did before.

4. **Docs.** `INSTALL.md` gains a *Quick start (the published image)* ahead
   of the from-source path: download two files, set the two paths,
   `docker compose -f compose.image.yml up -d`; how to pin a version and how
   to upgrade. `README.md`'s quick start mentions both. `RELEASING.md` gains
   the image steps: the tag, the workflow, the one-time visibility change,
   and a pull-and-run check of the published image.

## The one manual step

A GHCR package pushed by `GITHUB_TOKEN` starts **private**, so an anonymous
`docker pull` fails until its visibility is changed once, by a person with
the account, at
<https://github.com/users/danhon/packages/container/birdhouse/settings>.
`RELEASING.md` records it as a first-release step, with the anonymous pull
that proves it was done.

## How it is proven

Before the tag: `make test` (with the new parity test), and a local build of
the same Dockerfile served through `compose.image.yml` against this box's
BirdNET-Go paths, in a throwaway compose project, which exercises the whole
RELEASING checklist.

After the tag: the workflow's run is green; `docker pull` works without
credentials; `/healthz` in the published image reports the tagged commit;
the image-based stack again passes the checklist.

## Not in this change

- arm64 (Dan, 2026-11-27).
- Docker Hub, and any hosted or multi-user service.
- A nightly rebuild of the published image: a rebuild is a tag.
- Changing the reference deployment, which stays `make deploy` from source.
