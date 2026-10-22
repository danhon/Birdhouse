# Species List Overlay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Tapping "N species today" opens a full-screen veil over the current photo, listing every species shown in the carousel with a thumbnail. It's easy to dismiss and closes itself after 45s.

**Architecture:** Everything goes in `src/birdhouse/templates/index.html`. Jinja renders the overlay rows from the same `species` list as the slides. The existing inline script gets open/close, pause, auto-close, row-to-slide jump and deferred-reload logic. There are no server changes.

**Tech Stack:** Flask + Jinja2 template, inline CSS, plain ES5-style JS, pytest.

**Spec:** `docs/superpowers/specs/2026-10-22-species-list-overlay-design.md`, with the mockup at `docs/superpowers/specs/2026-10-22-species-list-overlay-mockups.html` (option A).

## Global Constraints

- All changes are in `src/birdhouse/templates/index.html`, plus tests and the README.
- Follow the file's conventions:
  - `/* ── Name ──── */` banners in CSS and `// ── Name ──` in JS
  - BEM-ish classes (`.overlay`, `.overlay__row`, …)
  - `function` and `const`/`let` in the IIFE, no frameworks
- Type: Georgia for names; system sans, uppercase, `letter-spacing: 0.04em` and `rgba(255,255,255,0.6)` for labels.
- Colour: white only, at the template's existing opacities.
- Veil: `rgba(0,0,0,0.72)` plus `backdrop-filter: blur(14px)` and `-webkit-backdrop-filter`.
- Gutters: list column max width about 720px, padding `3rem`, or `1.25rem` at `max-width: 600px`.
- Auto-close after 45 seconds of no interaction inside the overlay.
- No `inaturalist.org` links inside the overlay.

## Review Focus

1. **A tap on the count button advances the carousel.** It mustn't. The header is outside `#carousel`, so check that the click doesn't reach it. Verified by hand in Task 2.
2. **A deferred reload is lost.** If a poll changes the data while the overlay is open, closing must reload. Verified by hand in Task 2, with a lowered poll interval.
3. **Scroll chains to the page behind.** iPad Safari rubber-bands the body at the list ends. Use `overscroll-behavior: contain` on the list. Verified by hand on touch in Task 2.
4. **The auto-close timer isn't reset by scrolling.** Visitors reading a long list scroll rather than tap. Listen for `scroll`, `touchstart`, `pointerdown` and `keydown` on the overlay. Verified by hand in Task 2.
5. **A long common name ("Black-crowned Night Heron") pushes the meta column off-screen at phone width.** Use `min-width: 0` and an ellipsis on the names column. Verified by hand at 375px in Task 2.

---

### Task 1: Overlay markup, styles, and count button

**Files:**
- Modify: `src/birdhouse/templates/index.html`: CSS block, header markup, and a new overlay block after `.attribution`
- Test: `tests/test_app.py`: a new `TestSpeciesOverlay` class

**Interfaces:**
- Produces (DOM, for Task 2):
  - `button#species-count.header__count`, with `aria-expanded="false"` and `aria-controls="species-overlay"`
  - `div#species-overlay.overlay`, which has the `hidden` attribute, `role="dialog"`, `aria-modal="true"` and `aria-label="Species detected today"`, and is closed by default
  - Inside it:
    - `button.overlay__close`
    - `div.overlay__list` (the scroll container)
    - `button.overlay__row[data-index="{{ loop.index0 }}"]`, one per species
  - Each row contains:
    - either `img.overlay__thumb` (`loading="lazy"`, the same `object-position` as its slide) or `div.overlay__thumb overlay__thumb--empty`
    - `.overlay__common`, `.overlay__scientific` (a `div`, not an `a`), `.overlay__time` and `.overlay__count`
  - The overlay markup ends with the comment `<!-- /overlay -->`. Tests slice on it.
  - A CSS class `.overlay__row--current` for the highlight, which Task 2 toggles.

- [ ] **Step 1: Write the failing tests.** Add the helper `_overlay_html(data: bytes) -> str`, which returns the text from `id="species-overlay"` to `<!-- /overlay -->`. Fail if either marker is missing.

```python
class TestSpeciesOverlay:
    def test_count_is_a_button(self, client):
        _load_store([Species("American Crow", "Corvus brachyrhynchos", "8:00 am", 3)])
        data = client.get("/").data.decode()
        assert 'id="species-count"' in data
        assert re.search(r'<button[^>]*id="species-count"', data)
        assert "1 species today" in data

    def test_one_row_per_species_in_carousel_order(self, client):
        # crow (0), finch (1); assert data-index order and names appear in order
    def test_row_thumbnail_matches_slide(self, client):
        # image_path="Corvus_brachyrhynchos.jpg", focus_x=0.33, focus_y=0.21
        # overlay contains src="/images/Corvus_brachyrhynchos.jpg" and "object-position: 33.0% 21.0%"
    def test_row_placeholder_without_image(self, client):
        # image_path=None → "overlay__thumb--empty" in overlay
    def test_row_count_once_and_times(self, client):
        # counts 1 and 212 → overlay contains ">once<" and ">212×<"
    def test_row_shows_first_seen_and_scientific(self, client):
        # "8:00 am" and "Corvus brachyrhynchos" in overlay
    def test_overlay_has_no_inaturalist_links(self, client):
        # inat_id=123 → "inaturalist.org" not in overlay; "<a " not in overlay
    def test_overlay_closed_by_default(self, client):
        # re.search(r'id="species-overlay"[^>]*\bhidden\b', data)
    def test_no_overlay_in_empty_state(self, client):
        # empty store → "species-overlay" not in page
```

- [ ] **Step 2: Run them and check they fail.** Run `uv run pytest tests/test_app.py::TestSpeciesOverlay -v`. Expected: every test fails, because there's no overlay markup yet.

- [ ] **Step 3: Implement the markup and CSS.**
  - Swap the count `<span>` for `<button id="species-count" class="header__count" …>`. Keep `{{ species|length }} species today` as a single text node.
  - Add `.header__count { pointer-events: auto; font: inherit; color: inherit; background: none; border: 0; border-bottom: 1px solid rgba(255,255,255,0.35); padding: 0 0 2px; cursor: pointer; }`. Keep the existing size, colour and letter-spacing.
  - Overlay rules:
    - `position: fixed; inset: 0; z-index: 20`
    - the veil from Global Constraints
    - a flex column: top bar (date · count | `Close ✕`), then `.overlay__list` with `flex: 1; overflow-y: auto; overscroll-behavior: contain; -webkit-overflow-scrolling: touch`, scrollbar hidden, and a bottom fade via `mask-image` / `-webkit-mask-image`
    - fade-in uses `opacity`, with a transition of about 0.35s. Use an `.overlay--open` class on top of `hidden`, so the transition can run.
    - `@media (prefers-reduced-motion: reduce)` turns off the transition
  - Rows:
    - styled as plain text, using the same button reset as the count
    - a 64px thumb (48px at ≤600px) with `border-radius: 4px`
    - the hairline `rgba(255,255,255,0.08)`
    - common name: Georgia, `clamp(1.2rem, 2.4vw, 1.5rem)`, ellipsis
    - scientific name: Georgia italic at `rgba(255,255,255,0.65)`
    - time at 0.75 opacity, count at 0.45
    - `.overlay__row--current` gets the background `rgba(255,255,255,0.06)`
  - Use the mockup's option A as the visual reference.

- [ ] **Step 4: Run the whole suite and check it passes.** Run `uv run pytest -q`. Expected: everything passes, including the existing `test_species_count_in_header`.

- [ ] **Step 5: Commit.** Run `git add src/birdhouse/templates/index.html tests/test_app.py && git commit -m "Add species list overlay markup and styles"`.

### Task 2: Overlay behaviour

**Files:**
- Modify: `src/birdhouse/templates/index.html`: the inline script. Add a `// ── Species overlay ──` section, and change `tick` and `pollData`.

**Interfaces:**
- Consumes: the DOM from Task 1, plus the existing `showSlide(index)`, `current`, `startTime` and `tick`.
- Produces: none (this is the last task).

Behaviour:
- `openOverlay()`:
  - removes `hidden`, then adds `.overlay--open` on the next frame
  - sets `aria-expanded="true"`
  - marks the row whose `data-index == current` with `.overlay__row--current` and calls `scrollIntoView({block: 'center'})` on it
  - focuses `.overlay__close`
  - sets `overlayOpen = true`
  - starts the idle timer
- `closeOverlay(jumpTo)`:
  - reverses `openOverlay()` and clears the idle timer
  - if `jumpTo` is a number, calls `showSlide(jumpTo)`; otherwise sets `startTime = performance.now()`, so the slide gets a fresh full duration
  - focuses the count button
  - if `reloadPending`, calls `location.reload()`
- `tick`: while `overlayOpen`, doesn't advance or update the progress bar. Keep calling `requestAnimationFrame`.
- Idle timer: `const OVERLAY_IDLE_MS = 45000`. Reset it on `scroll` (on the list; use capture), `touchstart`, `pointerdown` and `keydown` (on the overlay).
- Closing triggers:
  - a click on the close button
  - a click whose target is the overlay itself or the list padding, i.e. not inside an `.overlay__row` or the top bar
  - the `Escape` key
  - a row click, which calls `closeOverlay(+row.dataset.index)`
- `pollData`: when the data has changed and `overlayOpen` is true, set `reloadPending = true` instead of reloading.

- [ ] **Step 1: Implement the behaviour above** in the existing IIFE.

- [ ] **Step 2: Run the suite.** Run `uv run pytest -q`. Expected: everything passes, since the markup is unchanged.

- [ ] **Step 3: Verify by hand in a browser.**
  - Run `PORT=8091 POLL_INTERVAL=10 uv run birdhouse` against the real DB, or seed the store.
  - Use a browser at iPad landscape size (1024×768), and at 375×667.
  - Check each of these:
    - Tapping the count opens the list, and the slide doesn't change.
    - The current species is highlighted and scrolled into view.
    - ✕ closes it.
    - Tapping the side margin closes it.
    - Esc closes it.
    - A row tap jumps to the right slide.
    - The progress bar is frozen while the list is open.
    - The list auto-closes 45s after the last scroll.
    - With the count check forced to differ (e.g. a temporary edit of `initSpeciesCount`), the page doesn't reload while the list is open, and reloads as soon as it closes.
    - Long names truncate at 375px.
    - There are no console errors.

- [ ] **Step 4: Commit.** Run `git commit -am "Add species list overlay behaviour"`.

### Task 3: README, push, deploy

**Files:**
- Modify: `README.md`, in the "Page layout" section

- [ ] **Step 1: Update the README.** Add this bullet: "Tap "N species today" to open a scrollable list of today's species over the current photo (thumbnail, names, first seen, count). Tap a bird to jump to its slide; tap ✕ or outside the list, press Esc, or wait 45 s to close it. The slideshow pauses while the list is open." Also change the top strip line to "date (left), species count (right, tappable)".
- [ ] **Step 2: Commit and push.** Run `git add README.md docs/ .gitignore && git commit -m "Document species list overlay" && git push origin main`.
- [ ] **Step 3: Deploy.** Run `make deploy`. Expected: the `birdhouse-app-1` container is recreated. Then `curl -s https://birdhouse.sgc.rayandhon.com/ | grep -c overlay__row` should give the live species count.
