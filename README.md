# Birdhouse

A full-bleed carousel of every bird species BirdNET-Go has heard today, in
order of first detection. Built for a wall-mounted screen, a monitor across
the room, or a phone: one photograph, the names, and a month of history
behind a tap.

Reference display: **[birdhouse.sgc.rayandhon.com](https://birdhouse.sgc.rayandhon.com)**
(Dan's own installation — public, no authentication).

Status: v0.1.0, MIT. One Birdhouse per BirdNET-Go installation; you run both.

---

## What it does

- Reads BirdNET-Go's SQLite database, not a camera stream, and shows each
  species once per day, merged across every BirdNET-Go model and filtered to
  birds.
- A full-bleed iNaturalist photograph, with its per-photo credit, plus the
  common and scientific names, first and last heard times, and detection
  count.
- A **last 30 days** history for any bird, opened by tapping its name: a bar
  per day against a detection axis, or a month calendar with each day's
  count. A Bars · Calendar switch flips between them.
- Tapping the day's species count opens today's list; ← / → step through the
  birds on a keyboard. The slideshow pauses while a panel is open and always
  finds its way back.
- Optionally crops each photo around the bird itself with Claude vision
  (needs an Anthropic key; a centre crop otherwise).
- Reloads itself when a new species appears or the date rolls over.

---

## Quick start

```bash
git clone https://github.com/danhon/Birdhouse.git
cd Birdhouse
cp .env.example .env
$EDITOR .env          # the two BirdNET-Go host paths
make run              # docker compose, http://127.0.0.1:8090
```

You need Docker and a BirdNET-Go whose database and `taxonomy.csv` Birdhouse
can read. **[INSTALL.md](INSTALL.md)** covers the paths, the preflight
diagnostics, upgrades and the public-page warning. If the page says it can't
read BirdNET-Go, start there.

---

## How it works

```
BirdNET-Go SQLite DB ──poll every 60s──► Birdhouse (Flask)
                                              │
                     iNaturalist API ─────────┤ (photo, name, credit; cached)
                        Claude API ───────────┤ (optional crop, once per species)
                                              │
                                    Browser ◄─┘ (server-rendered page)
```

Birdhouse mounts BirdNET-Go's database and `taxonomy.csv` read-only. It polls
the database every `POLL_INTERVAL` seconds, groups detections by scientific
name across all models, keeps only names whose taxonomy class is `aves`, and
renders a server-side page. Photos and their credits are fetched from
iNaturalist once and cached beside the image.

The REST API is used only to seed common names; if it is unavailable (or
BirdNET-Go's app login is on), iNaturalist names take over.

Reads are `immutable=1` against a single mounted file, so new detections
appear once BirdNET-Go checkpoints its WAL — usually a few minutes behind.

---

## Using it

- Click or tap anywhere on a slide to advance; swipe left/right on touch;
  ← / → on a keyboard.
- Tap **N species today** for the day's list. Tap a bird to jump to it.
- Tap a species' **common name** for its last 30 days. With the history open,
  ← / → take the bird and its history together.
- Everything that opens closes on ✕, Escape, a tap outside, or 45 seconds
  without interaction.

---

## Photos and credit

Photos come from the [iNaturalist](https://www.inaturalist.org) taxa API and
are cached to a Docker volume. Each cached photo keeps its photographer and
licence in a `.credit` sidecar; the page shows that credit and links to the
photo. Photos cached before credits existed are backfilled on the next poll.
The volume is the only state Birdhouse owns (besides the log), and it is
worth backing up if you have hand-edited crop anchors.

Smart cropping is one Claude vision call per species, cached forever. It is
off unless `ANTHROPIC_API_KEY` is set; without it photos use a centre crop.

---

## Documentation

| | |
|---|---|
| [INSTALL.md](INSTALL.md) | paths, first run, diagnostics, configuration, upgrades |
| [GLOSSARY.md](GLOSSARY.md) | operator, viewer, history, layout — the words this project uses |
| [SECURITY.md](SECURITY.md) | reporting a vulnerability; no auth by design |
| [RELEASING.md](RELEASING.md) | the checklist a release runs |
| [CHANGELOG.md](CHANGELOG.md) | what changed |
| [docs/adr/](docs/adr/) | why Birdhouse reads SQLite rather than BirdNET-Go's API |
| [docs/superpowers/](docs/superpowers/) | the history feature's design record |

---

## Development

```bash
uv sync --extra dev
make lint               # ruff's pyflakes rules: no unused imports or names
make check-template     # node --check on the rendered page's inline JS
make test               # all three; CI runs this
# Run outside Docker: the settings come from the environment, and the two
# BirdNET-Go paths are the files themselves, not the /data/ defaults.
BIRDNET_DB_PATH=/path/to/birdnet.db BIRDNET_TAXONOMY_PATH=/path/to/taxonomy.csv \
  uv run birdhouse      # gunicorn, on http://localhost:8090
```

`make check-template` needs Node. The repository is MIT-licensed
([LICENSE](LICENSE)); issues and pull requests are best-effort.
