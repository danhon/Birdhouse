# Releasing Birdhouse

There is no browser or Docker CI: the test suite guards the code, and a
release is gated by one fresh install that follows the stranger's path. Do
this before a tag, and record the result below.

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
