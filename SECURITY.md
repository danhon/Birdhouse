# Security

Birdhouse is a self-hosted display. It has **no authentication by design**:
anyone who can reach its URL sees the page. Keep it on a private network or
put it behind your own proxy authentication; see
[INSTALL.md](INSTALL.md#the-page-is-public).

## Reporting a vulnerability

Please use GitHub's private advisory form:

**https://github.com/danhon/Birdhouse/security/advisories/new**

Do not open a public issue for a vulnerability first. There is no
response-time promise; this is a best-effort personal project.

## What the app touches

- BirdNET-Go's `birdnet.db` and `taxonomy.csv`, read-only. Birdhouse never
  writes to them.
- The `birdhouse-images` volume: downloaded iNaturalist photos and their
  `.name`, `.id`, `.credit` and optional `.focus` sidecars.
- `ANTHROPIC_API_KEY`, read from the environment and used only for the
  optional one-time photo crop. It is never written into the cache or the
  page.
- The network: iNaturalist, BirdNET-Go's API for common names, and the
  Anthropic API when a key is set.

Application logs carry the request path, never query strings, bodies or
secrets.

## Supported versions

The current `main` and the latest release are supported on a best-effort
basis. See [INSTALL.md](INSTALL.md#compatibility) for the BirdNET-Go
compatibility statement.
