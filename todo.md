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

## Backend (`src/birdhouse/app.py`)

- [ ] `Config` gains `vision_enabled: bool` — computed once in
      `Config.from_env()` from whether `ANTHROPIC_API_KEY` is set. Vision
      logic is skipped entirely when false — checked once at startup, not
      per-species, per-poll.
- [ ] New `FOCUS_SCHEMA` (module constant) — `{visible: bool, bird_box:
      {x0,y0,x1,y1}, focus_x: number, focus_y: number}`,
      `additionalProperties: false` (validated shape — see above).
- [ ] New `_compute_focus_point(image_url: str, client) ->
      tuple[float, float] | None`:
  - Prompt: find the bird's whole-body bounding box, then its head (eye if
    visible, otherwise head center); return both. **Explicitly handle
    multiple birds** ("if more than one bird is visible, choose the most
    prominent or central one") — validated on the mallard-pair photo,
    correctly picked the foreground bird.
  - Clamp `(focus_x, focus_y)` into `bird_box` (not a fixed `[0.1, 0.9]`
    range as originally planned — the box-relative clamp is what actually
    fixed the observed failure; a fixed margin wouldn't have).
  - Use the model's `(x, y)` even when `visible: false` (a rough "somewhere
    on the bird" guess still beats dead-center) — `visible` is
    informational/logged, not a fallback trigger.
  - Returns `None` only on genuine failure: refusal (`stop_reason ==
    "refusal"`), unparseable response, or an exception — caller decides
    whether/when to retry based on **which** exception:
    - `anthropic.AuthenticationError` / `PermissionDeniedError` → bad or
      revoked key. Set a module-level `_vision_disabled = True` and log once
      at `error` level. Don't retry for the rest of the process lifetime —
      retrying a broken key every cycle forever is exactly the failure mode
      being designed against.
    - `anthropic.RateLimitError` / `APIConnectionError` / 5xx
      `APIStatusError` → transient. Apply the cooldown (below) and retry
      later. (Note: the SDK already auto-retries 429/5xx *within* one call
      with backoff — this cooldown is the *outer* layer across poll cycles,
      for when that also gets exhausted.)
    - Any other `APIStatusError` (e.g. 400 — malformed request, a code bug)
      or a JSON parse failure → log at `warning`, apply the cooldown too
      (avoids a hot loop if it's systematic) but don't disable permanently
      (could be a one-off).
- [ ] Module-level cooldown state: `_focus_cooldown: dict[str, float] = {}`
      (scientific_name → next-retry-timestamp). No lock needed — only ever
      touched from the single background poller thread, same threading
      model already used by `_name_cache`/`CommonNameCache`. Resets on
      restart — deliberately simple, no persisted backoff state.
- [ ] **Refactor `fetch_species_image` to a single exit point.** Currently
      it has three separate `return` statements, each reachable whenever
      `dest.exists()` is true (full cache hit, mid-function after an
      iNaturalist lookup, and after a fresh download). Focus-point
      computation needs to run once per code path, right before whichever
      return fires — cleanest as one internal step immediately before a
      single unified `return` at the bottom, rather than duplicating the
      check three times.
  - New sidecar file: `{filename}.focus` → `"0.46,0.32"` (plain text, same
    style as `.name`/`.id` — hand-editable).
  - Parse defensively like the existing `.id` parser
    ([app.py:171](src/birdhouse/app.py:171)): if the file doesn't split into
    two valid floats, fall back to `(0.5, 0.5)` rather than crashing
    template rendering.
  - Gate the vision call on: `config.vision_enabled`, `dest.exists()` (no
    point cropping a photo that doesn't exist), `.focus` file missing, and
    not in cooldown.
- [ ] Return signature becomes `(image_filename, common_name, inat_id,
      focus)` where `focus` is `tuple[float, float] | None` — a 4th element,
      not two new separate floats, to keep the tuple manageable.
- [ ] `Species` dataclass gains `focus_x: float = 0.5`, `focus_y: float =
      0.5` — safe defaults so nothing regresses if focus data is absent
      (feature disabled, cooldown, or genuine failure).
- [ ] `_refresh()` passes the new tuple element through into the `Species`
      constructor.

---

## Frontend (`src/birdhouse/templates/index.html`)

- [ ] Remove the static `object-position: center` rule from `.slide__photo`
      ([index.html:45-52](src/birdhouse/templates/index.html:45)).
- [ ] Add an inline style per slide on the `<img>` tag:
      `style="object-position: {{ (sp.focus_x*100)|round(1) }}% {{
      (sp.focus_y*100)|round(1) }}%"`. `object-fit: cover` is untouched —
      full-bleed guaranteed regardless of focus data.

---

## Config / docs

- [ ] Add `ANTHROPIC_API_KEY` to `.env.example` and `config.example.env`,
      documented as **optional** — "omit to disable smart cropping; falls
      back to a static center crop."
- [ ] Add to `compose.yml` env passthrough.
- [ ] README config table: add the `ANTHROPIC_API_KEY` row.
- [ ] README disk-cache table: add `{Scientific_name}.jpg.focus` →
      "Normalized focal point (x,y) for cropping, plain text" — and
      explicitly document it as hand-editable for manual correction (same
      override pattern as the existing `.name` sidecar).

---

## Tests

- [ ] `tests/test_image_cache.py`: existing tests unpack the current
      3-tuple from `fetch_species_image` — same failure mode as before (the
      tuple grew once already this session and broke 6 tests). Update all
      call sites to the new 4-tuple.
- [ ] New tests for `_compute_focus_point`, mocked via `unittest.mock.patch`
      — **not** the `responses` library fixture pattern already in this
      file, since that only intercepts `requests` and the `anthropic` SDK
      uses `httpx` under the hood. Cover: success, refusal, malformed JSON,
      `visible: false` (still uses returned coords), `AuthenticationError`
      (permanent disable), `RateLimitError` (cooldown applied, no permanent
      disable).
- [ ] Test the cooldown map directly: second call within the window is
      skipped without hitting the (mocked) client.

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

## Verification (after wiring in)

- [ ] `uv run pytest` green.
- [ ] Browser-tool screenshot comparison: iPad landscape (regression check
      — must look unchanged), plus 2–3 phone widths, using real species
      photos including the finch case above.
