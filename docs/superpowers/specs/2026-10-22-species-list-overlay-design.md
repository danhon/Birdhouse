# Species list overlay — design

Date: 2026-10-22
Status: approved in conversation, pending written-design review

## Intent

Birdhouse is a gallery-grade wall piece: an iPad (landscape) mounted on a
wall, cycling full-bleed photos of every bird species heard today. People
mostly glance at it from across the room. The header says "55 species
today", but there's no way to see *which* 55 without waiting through the
whole carousel.

This feature lets a visitor walk up, tap "55 species today", and read the
full list of today's species at arm's length, then walk away. The display
must always find its way back to the slideshow on its own.

## Goals

- Tapping/clicking the header's "N species today" opens an overlay listing
  every species shown in the carousel.
- The overlay looks like it belongs to the existing piece: same typography,
  same colour language, same restraint.
- The photo on screen at the time of the tap stays visible as the backdrop.
- Each row shows that species' own photo as a thumbnail.
- The list scrolls by touch; it's easy and obvious to dismiss.
- The wall never gets stuck on the overlay.

## Non-goals

- No server-side changes, new routes, or new data. Everything needed is
  already rendered into the page.
- No search, filter, sort controls, or species detail view.
- No change to how the carousel looks or what it shows.

## Anti-goals (failure even if it "works")

- It looks like a web app bolted onto an art piece: buttons, chrome, bright
  accent colours, system UI.
- The overlay is left open on the wall after the visitor walks away.
- The overlay vanishes under someone's finger because of the automatic
  reload.
- A tap takes the iPad away from Birdhouse (e.g. to iNaturalist).
- Opening the overlay also advances the carousel.

## Chosen layout: "A — full-screen veil, centred list"

Chosen by Dan from three mockups (A full-screen veil, B side panel, C photo
grid). Reference mockup:
`docs/superpowers/specs/2026-10-22-species-list-overlay-mockups.html`
(option A). (It loads photos from the live site; detection counts in it
are made up.)

- **Backdrop:** the current slide stays where it is. A full-viewport layer
  sits above everything at roughly `rgba(0,0,0,0.72)` with
  `backdrop-filter: blur(14px)` (plus `-webkit-backdrop-filter` for iPad
  Safari).
- **Top bar:** left, `{date_label} · {N} species today`; right, `Close ✕`.
  Both use the existing header label style (system sans, uppercase,
  `letter-spacing: 0.04em`, `rgba(255,255,255,0.6)`, `clamp(0.85rem,
  1.5vw, 1rem)`).
- **List:** a single centred column, max width about 720px, with page
  gutters of `3rem` on desktop/iPad and `1.25rem` at `max-width: 600px`,
  matching the existing `.header` / `.slide__info` paddings.
- **Row**, left to right:
  - Thumbnail: a square (about 64px at iPad size) of the species' cached
    photo (`/images/{{ sp.image_path }}`), `object-fit: cover`, with the
    same `object-position` from `focus_x`/`focus_y` as the slide, so the
    bird is centred in the thumb. Small radius (about 4px). If there's no
    image, use the existing `#1a1a2e` placeholder colour.
  - Names: common name in Georgia (about 1.5rem at iPad, single line,
    ellipsis); scientific name below in Georgia italic at
    `rgba(255,255,255,0.65)`, the same as the slide's scientific name. **Not a link.**
  - Meta, right-aligned: first-seen time (`rgba(255,255,255,0.75)`) and,
    below it, detection count (`rgba(255,255,255,0.45)`), shown as
    `once` / `212×` as in the mockup.
  - Rows are separated by a hairline `rgba(255,255,255,0.08)`.
- **Scroll hint:** the bottom edge of the list fades to the veil colour,
  so it reads as "there's more".
- **Order:** the same as the carousel (first detection, ascending).
- **Current species:** the row for the slide that was on screen when the
  overlay opened gets a subtle highlight (Claude's call: a faint
  `rgba(255,255,255,0.06)` background or a thin left rule; the builder
  picks whichever reads better). On open, the list scrolls so that row is
  visible.
- Use only type sizes and opacities that already exist in the template, or
  very close to them. No new fonts and no colours other than white at the
  template's opacities. The brightest text stays `#fff` for the common
  names.

## Behaviour

**Opening.**
- The header's count becomes the one interactive element in the header.
- Make it a `<button>` styled exactly like today's text, with a faint
  underline (`border-bottom: 1px solid rgba(255,255,255,0.35)`) to say
  "tappable".
- Reset the button's defaults (`font: inherit`, `color: inherit`,
  `background: none`, `border: 0` apart from the underline,
  `padding` as needed, `cursor: pointer`) so it looks exactly like
  today's text.
- `.header` stays `pointer-events: none`; only the button gets
  `pointer-events: auto`.
- The overlay fades in with the same feel as the slide crossfade (about
  0.3–0.4s; the slides use 0.8s, which is too slow for a response to a
  tap).
- Opening must not advance the carousel. The header isn't inside
  `#carousel`, so a click on the button won't reach the carousel's click
  handler. Verify this.

**Closing.** Any of these close the overlay:
- Tapping `Close ✕`.
- Tapping anywhere on the veil outside the list column, meaning the empty
  side margins and the space below the last row.
- Pressing `Escape`, for desktop use.
- Auto-close after **45 seconds** with no interaction inside the overlay
  (touch, scroll, or click). The timer restarts on each interaction.

**Tapping a row.** Closes the overlay and jumps the carousel to that
species' slide, restarting that slide's progress timer.

**While open.**
- The carousel is **paused**: no auto-advance, and the progress bar
  frozen.
- On close, it resumes. If you closed with ✕, the backdrop, or the
  timeout, the same slide continues with a fresh full duration (Claude's
  call: simpler than resuming the partial time, and harmless). A row tap
  goes to the chosen slide.
- The 60s `/data.json` poll keeps running. If it detects a change while
  the overlay is open, **defer** the `location.reload()` until the overlay
  closes, then reload right away.
- Touches and scrolls inside the overlay must not reach the carousel's
  swipe handlers. The overlay is a sibling of `#carousel`, not a child, so
  this should happen naturally. Verify it on touch.
- Scrolling: `overflow-y: auto`, `overscroll-behavior: contain`, and
  scrollbar hidden. A scroll gesture at the ends of the list must not
  move or bounce the page behind it.

**Accessibility and robustness (Claude's calls).**
- The overlay has `role="dialog"`, `aria-modal="true"`, and an
  `aria-label`.
- The count button has `aria-expanded`.
- Focus moves to Close on open and back to the count on close.
- Respect `prefers-reduced-motion` by dropping the fade.
- The empty state ("No birds yet today") has no header, so there's no
  overlay there. Nothing changes.

## Constraints

- All changes live in `src/birdhouse/templates/index.html`: markup, CSS and
  the existing inline IIFE script. Match the file's existing conventions:
  - section comment banners (`/* ── Name ──── */`, `// ── Name ──`)
  - BEM-ish class names (`.overlay`, `.overlay__row`, …)
  - plain ES5-style JS (`function`, `var`/`const`, no frameworks or
    build step)
- The overlay rows are rendered server-side by Jinja from the same
  `species` list as the slides, using `loop.index0` as the slide index.
  Don't rebuild them in JS.
- Thumbnails reuse the full-size cached images. There's no thumbnail
  endpoint; the browser has already loaded or cached them for the
  carousel. Use `loading="lazy"` on the thumbnails.
- Target: iPad Safari in landscape first. It must also stay usable on
  desktop browsers and in the existing phone-portrait layout
  (`max-width: 600px`).
- Update the README's "Page layout" section to mention the overlay.

## Testing

- **Server-rendered markup (pytest, `tests/test_app.py`)**:
  - Scope the checks to the overlay's markup only. The slides already
    contain "detected once today" and `inaturalist.org` links, so
    checking the whole page would pass or fail for the wrong reason.
  - The species count renders as a button.
  - The overlay contains one row per species, in carousel order.
  - Each row's thumbnail `src` and `object-position` match its slide.
  - The no-image placeholder renders in a row.
  - Detection count shows as `once` vs `N×`.
  - The overlay contains no `inaturalist.org` links.
  - The overlay is absent in the empty state.
- **Behaviour (JS)**: the repo has no JS test setup, and adding one is out
  of scope. Verify by hand in a browser against real data, ideally on the
  iPad itself:
  - open from the count
  - every way of closing
  - the 45s auto-close
  - row tap jumps to the right slide
  - carousel paused while open
  - deferred reload: trigger it by lowering `POLL_INTERVAL` or editing the
    count check, then close the overlay
  - no carousel advance or swipe from overlay touches
  - scroll contained
  - the phone-portrait layout

## Left to the builder

- Exact pixel sizes, spacing and easing, within "matches the existing
  template".
- Which highlight treatment to use for the current row.
- How to structure the JS state (an `overlayOpen` flag, a `paused` flag in
  `tick`, a pending-reload flag) inside the existing IIFE.
