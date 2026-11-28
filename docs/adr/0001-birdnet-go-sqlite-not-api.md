# 0001 — Read BirdNET-Go's SQLite file, not its API

Date: 2026-11-27
Status: accepted

## Context

Birdhouse needs today's detections and a species' last 30 days. BirdNET-Go
offers two ways in: its SQLite database (plus `taxonomy.csv`) and its REST
API. The database is exact and cheap to query for any window, and carries the
multi-model rows Birdhouse already merges. The API exposes detections too,
but asks for pagination, may be behind BirdNET-Go's own app login, and would
turn a month of history into a series of requests.

The cost of the database path is operational: the operator must mount the
file read-only, the app is a few minutes behind BirdNET-Go's WAL, and
restoring the database requires a restart because the single-file mount
pins the old inode.

## Decision

One supported data path: BirdNET-Go's **SQLite database plus
`taxonomy.csv`**. The REST API is optional and only seeds common names;
iNaturalist names take over when it is unavailable. A preflight checks the
tables and columns Birdhouse reads and reports a mismatch instead of showing
an empty page.

## Consequences

- The operator needs filesystem access to BirdNET-Go's data directory.
- The database shape becomes the compatibility contract. It is checked
  structurally, not by BirdNET-Go version.
- History stays a cheap local query, and all models are merged.
- No second adapter to maintain. An API-only or hybrid source would be a new
  decision, not a configuration flag.

## Alternatives considered

- **API only.** No mount, but pagination, auth and repeated requests; it
  also risks missing detections the API does not expose.
- **Both, switchable.** Two data paths to test and document, with two sets
  of failure modes, for an audience that already runs Docker.
- **Vendor a bird list instead of `taxonomy.csv`.** It goes stale with every
  BirdNET-Go upgrade, and the file is already on the operator's disk.
