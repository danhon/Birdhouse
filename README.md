# Birdhouse

A full-bleed bird species carousel showing every unique species detected today by BirdNET-Go, in order of first detection. Designed to be readable at a distance — wall-mounted TV, monitor across a room, or a phone.

Live at: `https://birdhouse.sgc.rayandhon.com` (public, no authentication)

---

## What it does

- Queries the BirdNET-Go SQLite database directly every 60 seconds
- Shows each unique species once, ordered by first detection time today
- Displays a full-bleed species photo (from iNaturalist, cached to disk), common name, scientific name, first-seen time, last-seen time, and detection count
- Optionally uses Claude vision to crop each photo around the bird itself rather than the frame center (requires `ANTHROPIC_API_KEY`; falls back to a center crop without it)
- Automatically reloads when a new species appears or the date rolls over
- Responsive layout for both large displays and mobile portrait

---

## Architecture

```
BirdNET-Go SQLite DB ──poll every 60s──► Birdhouse (Flask)
                                              │
                       iNaturalist API ───────┤ (once per species, cached to disk)
                    (photo, common name, ID)  │
                                              │
                          Claude API ─────────┤ (once per species, cached to disk;
                      (crop focal point)      │  optional — skipped without a key)
                                              │
                                    Browser ◄─┘ (server-rendered HTML + JS polling)
```

### Data flow

1. Background thread calls `query_today_from_db()` every `POLL_INTERVAL` seconds.
2. Queries `detections` JOIN `labels` for today's calendar day (local timezone), filtered to `confidence >= MIN_CONFIDENCE`. Returns `(scientific_name, first_seen_ts, last_seen_ts, count)` per species, sorted by `first_seen` ascending.
3. For each species, `fetch_species_image()` checks the disk cache, then calls the iNaturalist taxa API if not cached. Returns `(image_filename, common_name, inat_taxon_id, focus)`.
4. Common names come from the BirdNET-Go REST API (seeded on first unknown species); iNaturalist `preferred_common_name` is used as fallback.
5. When `ANTHROPIC_API_KEY` is set, `fetch_species_image()` also computes a crop focal point via a one-time Claude vision call (see "Smart photo cropping" below), cached to disk like everything else.
6. `DataStore` (thread-safe) holds the current species list, date label, and last-updated time.
7. `GET /` renders `index.html` with the current store snapshot.
8. `GET /data.json` returns `{date_label, species_count, last_updated}` for client-side polling.
9. Client JS polls `/data.json` every `POLL_INTERVAL` seconds and calls `location.reload()` if species count or date label changes.

**"Today"** = calendar date in the timezone set by `TZ` env var.

---

## Page layout

Full-bleed photo carousel. Each slide:

- Photo fills the entire viewport (`object-fit: cover`)
- Bottom gradient overlay for text legibility
- Bottom-left: common name (large serif), scientific name (italic, links directly to the iNaturalist taxon page), detection count + last seen time
- Bottom-right: first-seen time, slide counter ("3 of 12")
- Top strip: date (left), species count (right)
- Progress bar along the bottom edge
- Click or tap anywhere to advance; swipe left/right on mobile

---

## Repository layout

```
Birdhouse/
├── README.md
├── pyproject.toml
├── uv.lock
├── Dockerfile
├── compose.yml
├── Makefile
├── .env.example             ← all config vars documented; commit this
├── .gitignore               ← .env, data/, image-cache/ gitignored
├── src/
│   └── birdhouse/
│       ├── app.py           ← Flask app, DB query, image cache, polling
│       └── templates/
│           └── index.html   ← carousel template
├── tests/
│   ├── test_db.py
│   ├── test_app.py
│   ├── test_detections.py
│   ├── test_image_cache.py
│   └── test_focus_point.py
└── systemd/
    └── birdhouse.service    ← legacy; superseded by Docker Compose
```

---

## Configuration

Copy `.env.example` to `.env` and fill in values. All variables:

| Variable | Default | Description |
|---|---|---|
| `BIRDNET_BASE_URL` | `http://192.168.1.100:8888` | BirdNET-Go API (for common name seeding) |
| `BIRDNET_DB_HOST_PATH` | — | **Host** path to BirdNET-Go SQLite DB (Docker mount source) |
| `BIRDNET_DB_PATH` | `/data/birdnet.db` | Path inside the container (do not change) |
| `PORT` | `8090` | Port the app listens on |
| `MIN_CONFIDENCE` | `0.6` | Minimum detection confidence to display |
| `IMAGE_CACHE_DIR` | `/app/data/image-cache` | Species photo cache (backed by Docker volume) |
| `TZ` | `America/Los_Angeles` | Timezone for "today" |
| `POLL_INTERVAL` | `60` | Seconds between DB refreshes |
| `SLIDE_DURATION` | `8` | Seconds per carousel slide |
| `ANTHROPIC_API_KEY` | — (optional) | Enables vision-based smart photo cropping; omit to fall back to a center crop |
| `SERVICE_HOST` | `birdhouse.sgc.rayandhon.com` | Traefik routing hostname (set by Makefile) |

---

## Deployment

Birdhouse runs as a Docker Compose stack on ubuntuplex, discovered by Traefik via container labels.

```bash
# First time
cp .env.example .env
nano .env   # fill in BIRDNET_DB_HOST_PATH and other values

# Deploy (build image and start)
make deploy

# View logs
make logs

# Preview a branch at birdhouse-preview.sgc.rayandhon.com
make preview
```

See [python-apps.md](../reverse-proxy/docs-site/docs/services/python-apps.md) for the full pattern.

---

## Development

```bash
uv sync
uv run pytest           # run tests
uv run birdhouse        # run locally (reads from .env or env vars)
```

---

## Image and common name sources

**Photos:** iNaturalist taxa API — `results[0].default_photo.large_url`. Cached to `IMAGE_CACHE_DIR/{sanitised_scientific_name}.jpg`. Falls back to a dark background if unavailable.

**Common names:** BirdNET-Go REST API (`/api/v2/detections?limit=200`), seeded on first encounter. iNaturalist `preferred_common_name` used as fallback when BirdNET-Go doesn't have a name (e.g. rarer species not in the last 200 detections). Falls back to scientific name if neither source has it.

**iNaturalist taxon ID:** Stored alongside the photo and common name so links go directly to `inaturalist.org/taxa/{id}` rather than a search page.

**Smart photo cropping:** When `ANTHROPIC_API_KEY` is set, each species' photo gets a one-time Claude vision call (`claude-opus-4-8`, structured output) that locates the bird's head/eye and returns a normalized crop anchor. The carousel's `object-fit: cover` stays full-bleed on every viewport; only the crop anchor (`object-position`) moves, so mobile portrait crops stay centered on the bird instead of the geometric center of the photo. Computed once per species, cached forever — never recomputed on later polls. Without a key, photos fall back to a plain center crop, same as before.

### Disk cache layout

Each species produces up to four sidecar files in `IMAGE_CACHE_DIR`:

| File | Contents |
|---|---|
| `{Scientific_name}.jpg` | Cached photo from iNaturalist |
| `{Scientific_name}.jpg.name` | Common name (plain text) |
| `{Scientific_name}.jpg.id` | iNaturalist taxon ID (integer, plain text) |
| `{Scientific_name}.jpg.focus` | Crop anchor as `x,y` normalized coordinates (plain text) — only written when smart cropping is enabled |

The `.name`, `.id`, and `.focus` files are all plain text and safe to hand-edit — delete one to force a fresh lookup, or edit `.focus` directly to manually correct a crop that doesn't look right. The `.name`/`.id` pair must both exist for the cache to be considered complete; a missing one triggers a fresh iNaturalist API call. Browse the cache with:

```bash
docker run --rm -v birdhouse_birdhouse-images:/cache alpine ls /cache
```
