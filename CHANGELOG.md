# Changelog

Notable changes to Birdhouse. The format is loosely Keep a Changelog; the
version is the git tag.

## v0.1.0 — 2026-11-27

First public release.

- A full-bleed, self-advancing carousel of today's bird species, merged
  across BirdNET-Go's models and filtered to birds.
- A 30-day history for a species, opened by tapping its common name: a bar
  per day against a detection axis, or a month calendar with each day's
  count. A Bars · Calendar switch flips between them in place.
- Per-photo credits from iNaturalist, cached beside each photo; existing
  photo caches are backfilled.
- The species list for today, keyboard stepping with ← / →, and a panel that
  always closes itself.
- A preflight for BirdNET-Go's database and `taxonomy.csv`, with a
  diagnostic page naming what is wrong.
- Docker Compose install; SQLite as the single data path; optional Anthropic
  smart cropping.
