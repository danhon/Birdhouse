# Installing Birdhouse

Birdhouse is self-hosted: one Birdhouse next to one BirdNET-Go installation.
It reads BirdNET-Go's SQLite database and `taxonomy.csv` read-only, and
serves a page. You need Docker with Compose, and a BirdNET-Go whose data
directory you can mount.

## Before you start

You need two files from BirdNET-Go on the machine running Birdhouse:

- **`birdnet.db`** — its SQLite database (usually `data/birdnet.db`).
- **`taxonomy.csv`** — its taxonomy (usually
  `config/models/shared/taxonomy.csv`).

Both are mounted as files, not directories. If BirdNET-Go runs on another
machine, mount its data directory over NFS/SMB or run Birdhouse there;
BirdNET-Go's REST API is not a substitute for the database.

Birdhouse is tested with **BirdNET-Go 20261031**. See
[Compatibility](#compatibility).

## Quick start (the published image)

Birdhouse's image is for **linux/amd64**. Nothing is built: two files, one
command. You still need the two BirdNET-Go files from
[Before you start](#before-you-start).

**No image is published yet.** The image install begins with the next
release, `v0.1.1`; until then, build from source with
[Configure](#configure) and [Run](#run) below. If the pull says
`manifest unknown` or `denied`, that release isn't out, or its package isn't
public yet — use the source install.

In `.env`, besides the two host paths:

- If BirdNET-Go runs on this machine, set
  `BIRDNET_BASE_URL=http://host.docker.internal:8080` — the compose file
  provides that hostname. The default, `birdnet-go:8080`, doesn't resolve
  there, and common names fall back to iNaturalist.
- To pin a version, set `BIRDHOUSE_IMAGE_TAG=v0.1.1`. Put it in `.env`, not
  only on the command line, so a later `pull` and `up` agree; without it you
  get `ghcr.io/danhon/birdhouse:latest`.

```bash
mkdir birdhouse && cd birdhouse
curl -fsSLO https://raw.githubusercontent.com/danhon/Birdhouse/main/compose.image.yml
curl -fsSL https://raw.githubusercontent.com/danhon/Birdhouse/main/.env.example -o .env
$EDITOR .env            # the two BirdNET-Go host paths, and the two lines above
mkdir -p logs
docker compose -f compose.image.yml up -d
# then open http://127.0.0.1:8090
```

Everything else applies to either install. **Configure**'s clone steps and
`make run` in **Run** are the source install only; if you used the image,
skip those, but read [Configuration](#configuration) for what the `.env`
values mean, and run the three-point check under **Run** to see that it
works. [When the page says it can't read BirdNET-Go](#when-the-page-says-it-cant-read-birdnet-go)
covers a diagnostic page.

## Configure

```bash
git clone https://github.com/danhon/Birdhouse.git
cd Birdhouse
cp .env.example .env
$EDITOR .env
```

Set the host paths:

```ini
BIRDNET_DB_HOST_PATH=/home/you/birdnet-go/data/birdnet.db
BIRDNET_TAXONOMY_HOST_PATH=/home/you/birdnet-go/config/models/shared/taxonomy.csv
BIRDNET_BASE_URL=http://birdnet-go:8080
```

`BIRDNET_BASE_URL` is how the container reaches BirdNET-Go's API for common
names. With `make run` and BirdNET-Go on the same host, use
`http://host.docker.internal:8080`; the included override maps that on Linux.

## Run

```bash
make run
# then open http://127.0.0.1:8090
```

The first load fetches a photo for each species from iNaturalist, so a busy
day can take a moment. A working page shows a photograph, a credit in the
bottom-right corner, and a species count.

Check the three things that matter:

1. A slide with the day's birds and a **photo credit**.
2. **N species today** opens the list.
3. Tapping a **common name** opens its last 30 days.

## When the page says it can't read BirdNET-Go

Birdhouse checks its inputs on every poll. If one is wrong it shows a
diagnostic page instead of a convincing empty morning, and retries every
minute — fix the problem and wait, or reload.

| The page says | Check |
|---|---|
| "database isn't at /data/birdnet.db" | `BIRDNET_DB_HOST_PATH` is the file itself, not its folder; the mount exists |
| "database … could not be read" | the path is a file BirdNET-Go wrote, readable by the container; not a directory or a half-copied backup |
| "has no labels/detections table" or "is missing …" | that it is the database from the supported schema (below), not an old copy or a different app's |
| "taxonomy.csv isn't at /data/taxonomy.csv" | `BIRDNET_TAXONOMY_HOST_PATH`, again the file itself |
| "taxonomy.csv is missing the sci_name/class_name column" | it is BirdNET-Go's `config/models/shared/taxonomy.csv` |

## Compatibility

Birdhouse is tested with **BirdNET-Go 20261031**. It reads the `labels` and
`detections` tables and the `taxonomy.csv` columns `sci_name` and
`class_name`; a newer BirdNET-Go is likely to work while those stay. The
preflight is the contract: it names the exact table or column that moved
instead of showing an empty page. There is no version matrix yet.

## Configuration

| Variable | Default | Description |
|---|---|---|
| `BIRDNET_BASE_URL` | `http://birdnet-go:8080` | BirdNET-Go API for common-name seeding, as the container reaches it |
| `BIRDNET_DB_HOST_PATH` | — | **Host** path to BirdNET-Go's SQLite database (Docker mount source) |
| `BIRDNET_DB_PATH` | `/data/birdnet.db` | Path inside the container (leave it) |
| `BIRDNET_TAXONOMY_HOST_PATH` | — | **Host** path to BirdNET-Go's `taxonomy.csv` (Docker mount source) |
| `BIRDNET_TAXONOMY_PATH` | `/data/taxonomy.csv` | Path inside the container (leave it) |
| `PORT` | `8090` | Port gunicorn binds; the compose files and healthcheck assume it |
| `MIN_CONFIDENCE` | `0.6` | Minimum detection confidence to display |
| `IMAGE_CACHE_DIR` | `/app/data/image-cache` | Photo cache, backed by the `birdhouse-images` Docker volume (leave it) |
| `TZ` | `America/Los_Angeles` | Timezone for "today" and the history's day boundaries |
| `POLL_INTERVAL` | `60` | Seconds between database refreshes |
| `SLIDE_DURATION` | `8` | Seconds each slide is shown |
| `ANTHROPIC_API_KEY` | — | Optional; enables the one-time smart photo crop |
| `BIRDHOUSE_IMAGE_TAG` | `latest` | Image install only: the version to run |
| `BIRDHOUSE_LOG_DIR` | `./logs` | **Host** folder for `app.log` (JSON lines) |

### Common names

BirdNET-Go's API supplies the common names. If it is unreachable, or its app
login is on, Birdhouse uses iNaturalist's preferred common name instead; a
missing common name is cosmetic. There is no BirdNET-Go API token support.

### Smart cropping

With `ANTHROPIC_API_KEY` set, each species gets one Claude vision call to
find the bird's head and anchor the crop there; the result is cached forever
and never recomputed. Without a key, photos use a centre crop. The key is
only used at photo-cache time.

## The page is public

**Birdhouse has no authentication.** Anyone who can reach the URL sees every
bird and the exact times it was heard. Those times can reveal when a house is
empty. If that matters, put the page behind your own proxy authentication
(for example Traefik with Authelia) or keep it on a private network. The app
does not need to be exposed to the internet; the reference display is, by
choice.

Do not expose BirdNET-Go's API or database to the internet for Birdhouse's
sake. Birdhouse only needs the mounted files.

## Upgrades, the cache and backups

- **Image install:** `docker compose -f compose.image.yml pull`, then
  `up -d` again; change `BIRDHOUSE_IMAGE_TAG` to move to another version.
  The photo cache volume persists. It is named after the folder you run in,
  so an image install and a source install in folders of the same name
  (`birdhouse`) share it.
- **Source install:** pull a new commit and run `make run` again; the image
  rebuilds and the photo volume persists.
- The photo cache is the `birdhouse-images` Docker volume. It holds each
  photo and its `.name`, `.id`, `.credit` and optional `.focus` sidecars.
  Back it up if you have hand-edited crop anchors; the rest can be fetched
  again.
- The database is opened read-only with `immutable=1`, so detections appear
  when BirdNET-Go checkpoints its WAL — usually minutes behind. If you
  restore BirdNET-Go's database from a backup (a new file), restart
  Birdhouse: the single-file mount still points at the old one.
- The app holds no other state.

## Troubleshooting

- **"No birds yet today" on a day with detections.** Birdhouse is a few
  minutes behind BirdNET-Go's WAL, or `TZ` is wrong. Check the date at the
  top of the page.
- **Names are scientific, not common.** The BirdNET-Go API was unreachable
  (or its app login is on); iNaturalist names are the fallback. This is
  cosmetic.
- **A bird has no photo.** iNaturalist had no result or the download failed;
  Birdhouse retries on the next poll. Check the log for the species name.
- **The history panel says unavailable.** The database query failed for that
  species; the diagnostic page covers a broken database, but a transient read
  can affect one request. Close and reopen it.
- **First start is slow.** Photos are being fetched and cached. The page is
  usable as each arrives.
