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
      missing file, confirm the page names it, then restore and confirm the
      carousel recovers without a restart.
- [ ] Stop and remove the check's compose project and photo volume.

## The v0.1.0 run

Not yet run.
