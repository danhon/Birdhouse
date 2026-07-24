# Smart photo cropping (vision-based focal point)

Goal: keep bird photos full-bleed (`object-fit: cover`, never letterboxed) but
anchor the crop on the bird instead of the geometric center, so mobile
portrait crops don't amputate the subject. Computed once per species via a
Claude vision call at cache time; served via a per-photo `object-position`.

Full-bleed is non-negotiable — this only ever changes *where* the frame is
anchored, never whether the photo fills it.

---

## Design decisions (locked in)

- **One vision call per species, ever** — not per page load, not per poll
  cycle. Cached to disk forever, same pattern as the existing `.name`/`.id`
  sidecar files.
- **Model:** `claude-opus-4-8`, no `effort` override (defaults to `high`) —
  volume is a few dozen calls total, ever, so cost is not a real constraint;
  precision is what matters for spatial grounding.
- **Structured output** (`output_config.format` json_schema) — not prefill
  (rejected on Opus 4.8 anyway) — so the response is guaranteed parseable.
- **Image passed by URL**, not base64 — `fetch_species_image` already has
  `image_url` in scope before download; no need to read cached bytes back off
  disk and re-encode them.
- **Feature is fully optional** — no `ANTHROPIC_API_KEY` set → app behaves
  exactly as it does today (static center crop), no errors, no log spam.

---

## Validated (2026-07-23)

Ran a standalone script against 8 real iNaturalist photos (crow, house
finch, Steller's jay, mallard pair, black-capped chickadee, junco, mourning
dove, white-crowned sparrow) via `claude-opus-4-8` + structured outputs.

- **First pass** (head/eye point only): 7/8 correct. One **repeatable**
  miss on the chickadee — reran 4x, x-coordinate landed wrong every time
  (0.21–0.44 vs. the bird's actual ~0.64), while y was consistently
  plausible. Not noise — a real, consistent perception error on that
  composition (busy branch clutter).
- **Fix:** also ask for a bounding box of the bird's whole body in the same
  call, then clamp the head point into that box. This wasn't just a
  clamp-based safety net — asking for the box *changed the model's own head
  estimate* (it stopped scattering and converged on the right answer,
  landing dead-on the eye). Re-ran the full batch afterward: 8/8 correct,
  nothing regressed.
- **Conclusion:** ship the bounding-box version, not the plain point-only
  version from the original plan.

## Backend (`src/birdhouse/app.py`) — implemented

- [x] `Config` gains `vision_enabled: bool` — computed once in
      `Config.from_env()` from whether `ANTHROPIC_API_KEY` is set.
- [x] `FOCUS_SCHEMA` module constant — `{visible, bird_box: {x0,y0,x1,y1},
      focus_x, focus_y}`, `additionalProperties: false` (validated shape).
- [x] `_get_or_compute_focus(scientific_name, image_path, focus_file,
      client) -> tuple[float, float] | None` — sends the **already-cached
      local file's bytes** (base64), not the iNaturalist URL as originally
      planned. Reasoning: the "fully cached, no network call needed" path
      (all sidecars present) never has a fresh `image_url` in scope — only
      the local `dest` path is guaranteed to exist wherever focus
      computation runs. Base64-from-disk is also exactly what the
      validation script tested, so it's the actually-validated path, not
      an untested variant.
  - Prompt asks for the bird's whole-body bounding box + head point in one
    call; multiple-bird tie-break instruction included (validated on the
    mallard pair).
  - `(focus_x, focus_y)` clamped into `bird_box` via `_clamp_focus_to_box`.
  - Cached focus file parsed defensively (bad split/float → log + fall
    through to recompute) — same defensive spirit as the `.id` parser.
  - Two-tier exception handling, not three — `RateLimitError` is itself an
    `APIStatusError` subclass, so "transient" and "other API error" collapse
    to identical cooldown treatment; only auth errors need distinct
    (permanent-disable) handling:
    - `AuthenticationError` / `PermissionDeniedError` → `_vision_disabled =
      True` (module-level), logged once at `error`. Never retried again
      this process.
    - `APIStatusError` / `APIConnectionError` (covers rate limits, 5xx,
      other 4xx, and connection failures) → cooldown applied, logged at
      `warning`.
    - `stop_reason == "refusal"` and JSON parse failures → same cooldown
      treatment.
  - Uses the model's `(x, y)` regardless of `visible` — informational only.
- [x] Module-level `_focus_cooldown: dict[str, float]` + `_vision_disabled`
      flag, unlocked (single poller thread), 1-hour cooldown window.
- [x] **Refactor, but not literally "single exit point."** Instead of
      flattening `_fetch_image_metadata`'s three existing `return`s (real
      risk of subtly changing already-tested iNaturalist-failure-handling
      behavior for no real benefit), left that function's body untouched
      and wrapped it: `fetch_species_image()` now calls
      `_fetch_image_metadata()` for the existing 3-tuple, then computes
      focus once in one place using its result, then returns the 4-tuple.
      Same practical goal (one call site for focus logic) with a much
      smaller, lower-risk diff on working code.
  - New sidecar file `{filename}.focus`, gated on `config.vision_enabled`,
    `image_filename` truthy (image actually cached), file missing, and
    not in cooldown/disabled.
- [x] Return signature: `(image_filename, common_name, inat_id, focus)`,
      `focus: tuple[float, float] | None`.
- [x] `Species` gains `focus_x: float = 0.5`, `focus_y: float = 0.5`.
- [x] `_refresh()` / `start_background_poller()` construct
      `anthropic.Anthropic()` once (only when `vision_enabled`) and thread
      it through to `fetch_species_image()`, same pattern as the existing
      `requests.Session`.
- [x] Added `anthropic` to `pyproject.toml` dependencies.

---

## Frontend (`src/birdhouse/templates/index.html`) — implemented

- [x] Removed the static `object-position: center` rule from `.slide__photo`.
- [x] Added an inline style per slide on the `<img>` tag driven by
      `sp.focus_x`/`sp.focus_y`. `object-fit: cover` is untouched —
      full-bleed guaranteed regardless of focus data.

---

## Config / docs

- [x] Add `ANTHROPIC_API_KEY` to `.env.example` and `config.example.env`,
      documented as **optional** — "omit to disable smart cropping; falls
      back to a static center crop."
- [x] ~~Add to `compose.yml` env passthrough~~ — not needed, `compose.yml`
      already does `env_file: .env`, which passes every variable through;
      there's no per-variable allowlist to edit.
- [x] README config table: add the `ANTHROPIC_API_KEY` row.
- [x] README disk-cache table: add `{Scientific_name}.jpg.focus` →
      "Normalized focal point (x,y) for cropping, plain text" — and
      explicitly document it as hand-editable for manual correction (same
      override pattern as the existing `.name` sidecar).

---

## Tests — implemented (11 new tests, 62/62 passing)

- [x] `tests/test_image_cache.py`: updated existing tests to the new
      4-tuple. Also added one integration test wiring a mocked vision
      client all the way through `fetch_species_image()`, not just testing
      `_get_or_compute_focus()` in isolation.
- [x] `tests/test_focus_point.py` (new file): `_get_or_compute_focus`
      tested via plain `unittest.mock.MagicMock` on the client (confirmed
      `responses` doesn't apply — `anthropic` uses `httpx`, not `requests`).
      Covers: success + sidecar write, box-relative clamping, `visible:
      false` still using the returned coords, cache hit (no API call),
      malformed cache file (recomputes), refusal, malformed JSON,
      `AuthenticationError` (permanent disable, verified a second call for
      a *different* species also short-circuits), `RateLimitError` and
      `APIConnectionError` (cooldown, verified a second call within the
      window doesn't hit the client again).

---

## Validation (before wiring into the app)

- [x] Standalone script against real cached photos, not synthetic ones.
      Adversarial sample covered: the house finch case that already failed
      under plain `smartcrop`, branch-clutter obscuring the head
      (chickadee), two birds in one photo (mallard pair, tie-break check).
      See "Validated" section above for the full result and the
      bounding-box fix it led to.
- [x] Render crosshair overlays on results for eyeballing, same as the
      earlier `smartcrop` feasibility check.
- [x] Proceed to wiring into `app.py` — schema/prompt validated 8/8 on the
      test sample after the bounding-box fix.

## Verification (after wiring in) — done

- [x] `uv run pytest` green (62/62).
- [x] End-to-end real-data check: a throwaway script seeded the live app
      with 6 real species by calling the actual `fetch_species_image()` —
      real iNaturalist + real Claude vision calls, not mocks — then ran the
      Flask dev server for the Browser tool to screenshot.
- [x] Desktop/landscape (regression check): full-bleed, unchanged from
      before — object-position defaults render fine.
- [x] Mobile portrait (375×812), all 6 species: crow, jay, dove, mallard
      pair (correctly on the foreground bird), and — the two cases that
      mattered most — **house finch** (the original `smartcrop` failure:
      head fully in frame, not clipped) and **black-capped chickadee** (the
      case that needed the bounding-box fix: dead-on the eye). All
      full-bleed, no letterboxing, anchored on the bird in every case.
