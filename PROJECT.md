# Birdhouse

A single-page public display showing every unique bird species detected today by BirdNET-Go, in order of first detection. Designed to be readable at a distance — wall-mounted TV, monitor across a room, or a browser.

Live at: `https://birdhouse.sgc.rayandhon.com`

---

## What it does

- Polls the BirdNET-Go REST API for today's detections every 60 seconds
- Shows each unique species once, ordered by the time it was first detected today
- Displays a representative species photo (from iNaturalist), common name, scientific name, and first-seen time
- Auto-refreshes the page every 60 seconds — no JavaScript framework needed

---

## Architecture

```
BirdNET-Go API ──poll every 60s──► Birdhouse (Flask)
                                        │
                     iNaturalist API ───┤ (one-time per species, cached to disk)
                                        │
                              Browser ◄─┘ (server-rendered HTML, meta-refresh)
```

### Data flow

1. On each page request (or background refresh), fetch `GET /api/v2/detections?date=YYYY-MM-DD&limit=200` from BirdNET-Go, paginating if `total_pages > 1`.
2. Filter to detections at or above `MIN_CONFIDENCE` (default 0.6).
3. Group by `scientificName`; keep the **earliest** `time` per species.
4. Sort ascending by first-detection time — this is the display order.
5. For each species, look up a photo from the iNaturalist API (`GET https://api.inaturalist.org/v1/taxa?q={scientific_name}&rank=species`), using `results[0].default_photo.medium_url`. Cache to disk by scientific name.
6. Render the Jinja2 template and return HTML with `<meta http-equiv="refresh" content="60">`.

**"Today"** = calendar date in ubuntuplex's local timezone, derived from `TZ` env var (`America/Los_Angeles`).

---

## Page layout

```
┌──────────────────────────────────────────────────────┐
│  Birdhouse                  Tuesday 13 May 2026      │
│  14 species today                                     │
├──────────────────────────────────────────────────────┤
│ [photo]  American Crow                    5:24 pm    │
│          Corvus brachyrhynchos                        │
│                                                       │
│ [photo]  House Finch                      5:26 pm    │
│          Haemorhous mexicanus                         │
│   ...                                                 │
└──────────────────────────────────────────────────────┘
```

- **Header**: "Birdhouse" left, full date right; "N species today" subtitle
- **Each row**: square photo (~120×120 px) left; common name (large, bold) and scientific name (smaller, italic) stacked; first-seen time right-aligned
- **Colour scheme**: dark background (`#111`), white/off-white text — high contrast for distance legibility
- **Typography**: system-ui or Inter, common name ~2rem, scientific name ~1rem muted, time ~1rem muted
- **No interactivity** — pure display, no nav, no clicks

---

## Repository layout

```
Birdhouse/
├── PROJECT.md               ← this file
├── pyproject.toml
├── config.example.env
├── src/
│   └── birdhouse/
│       ├── __init__.py
│       ├── app.py           ← Flask app: polling, image cache, route
│       └── templates/
│           └── index.html   ← Jinja2 template
├── data/
│   └── image-cache/         ← cached species photos (gitignored)
└── systemd/
    └── birdhouse.service    ← systemd user unit template
```

---

## Configuration

Copy `config.example.env` to `config.env` (or `~/.config/birdhouse/env` for systemd) and edit:

| Variable | Default | Description |
|---|---|---|
| `BIRDNET_BASE_URL` | `http://192.168.1.100:8888` | BirdNET-Go API base |
| `PORT` | `8090` | Port Birdhouse listens on |
| `MIN_CONFIDENCE` | `0.6` | Minimum detection confidence to include |
| `IMAGE_CACHE_DIR` | `data/image-cache` | Directory for cached species photos |
| `TZ` | `America/Los_Angeles` | Timezone for determining "today" |
| `POLL_INTERVAL` | `60` | Seconds between background data refreshes |

---

## Ports in use on ubuntuplex (reference)

| Port | Service |
|---|---|
| 80 / 443 | Traefik |
| 8213 | Buywanderbot |
| 8581 | Homebridge |
| 8787 | BirdNET Analytics |
| 8888 | BirdNET-Go |
| 9080 | Pi-hole |
| 9091 | Authelia |
| 11080 | Scrypted |
| 61208 | Glances |
| **8090** | **Birdhouse ← assigned** |

---

## Deployment

### 1. Clone and install

```bash
git clone <repo> ~/dev/Birdhouse
cd ~/dev/Birdhouse
~/.local/bin/uv sync
```

### 2. Configure

```bash
mkdir -p ~/.config/birdhouse
cp config.example.env ~/.config/birdhouse/env
nano ~/.config/birdhouse/env
```

### 3. Systemd user service

Copy or symlink `systemd/birdhouse.service` to `~/.config/systemd/user/birdhouse.service`, then:

```bash
systemctl --user daemon-reload
systemctl --user enable --now birdhouse
journalctl --user -u birdhouse -f
```

### 4. Traefik route

Create `~/dev/reverse-proxy/traefik/dynamic/birdhouse.yml`:

```yaml
http:
  routers:
    birdhouse:
      rule: Host(`birdhouse.sgc.rayandhon.com`)
      entrypoints: [websecure]
      tls:
        certResolver: le
      service: birdhouse
      middlewares: [authelia@file]

  services:
    birdhouse:
      loadBalancer:
        servers:
          - url: http://host.docker.internal:8090
```

Traefik hot-reloads — no restart needed.

### 5. Verify

```bash
curl http://localhost:8090/          # should return HTML
dig @127.0.0.1 birdhouse.sgc.rayandhon.com  # should resolve to 192.168.1.100
```

---

## Image source

Photos come from the **iNaturalist API** — free, no authentication required.

Request:
```
GET https://api.inaturalist.org/v1/taxa?q={scientific_name}&rank=species&per_page=1
```

Response field used: `results[0].default_photo.medium_url`

Photos are cached to `IMAGE_CACHE_DIR/{sanitised_scientific_name}.jpg` on first fetch. If iNaturalist returns no result or the request fails, the row displays without a photo (graceful degradation — no broken image icons).

---

## Out of scope (for now)

- History / previous-day pages
- Detection count per species
- Audio spectrograms
- Manually-verified-only filter
- Mobile-optimised layout
- Authentication (add `authelia@file` middleware if wanted; omit if you want it open)

---

## Implementation plan

### Phase 1 — Core app

- [ ] `pyproject.toml` with Flask + python-dateutil dependencies
- [ ] `src/birdhouse/app.py`:
  - BirdNET-Go polling: fetch today's detections, paginate, dedupe by scientific name, sort by first detection
  - iNaturalist image fetch + disk cache
  - Flask route `/` → render template
  - Background thread refreshing data every `POLL_INTERVAL` seconds
- [ ] `src/birdhouse/templates/index.html`: dark-background display layout
- [ ] `config.example.env`

### Phase 2 — Deployment

- [ ] `systemd/birdhouse.service` unit file
- [ ] `traefik/dynamic/birdhouse.yml` route in reverse-proxy repo
- [ ] `.gitignore` (data/, image-cache/, .venv/, config.env)
- [ ] Deploy to ubuntuplex and smoke-test

### Phase 3 — Polish

- [ ] Graceful handling of BirdNET-Go being unreachable (show last known data + "last updated" timestamp)
- [ ] Placeholder silhouette image when iNaturalist returns nothing
- [ ] README with setup instructions
