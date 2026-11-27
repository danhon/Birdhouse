# A species' last 30 days — design

Date: 2026-11-27
Status: approved in conversation (Dan chose the two layouts and their refinements)

## Intent

Birdhouse shows what is being heard *today*. Once a bird is on screen,
the next question from across the room is "is it always here, or is this
the first time?" This adds that month of context, opened by tapping the
bird's name on its slide.

The display is a gallery-grade wall piece: full-bleed photograph, Georgia
for names, system sans for labels, white only. The history is a placard
over the photograph, not a dashboard.

## Goals

- Tapping a species' **common name** on its slide opens its last 30 days
  over the current photo.
- Two readings, chosen by the page URL:
  - `strip` (default): one bar per day, with a count y-axis.
  - `?history=field`: a five-week calendar whose squares carry each day's
    detection count.
- Same veil, pause, idle-close and deferred-reload behaviour as the
  species list: it belongs to the piece and can never get stuck.
- The slide's own caption fades out while a history is open, leaving only
  the photograph behind the veil.

## Non-goals

- No time-of-day history (a day-by-hour raster was built, shown and
  dropped: too dense for the wall).
- No per-day drill-down, filters or links out.
- No change to the carousel or today's list.
- No remembered layout *per species*: one choice applies to every
  history on the display.

## Chosen layouts

### Strip (default)

Bars sit on a baseline; a y-axis at the left has three or four round
labels (0, 200, 400, 600), chosen from the view's own maximum with a
"nice step" (1, 2, 2.5, 5 × 10ⁿ, whole numbers only for small maxima).
The scale is **linear**; with a labelled axis there is no reason to
square-root it. Days with detections of 1 use the bar's 2px minimum so a
trickle beside a spike stays visible. Zero days are a 2px stub at 10%
white. Today's bar is the brightest. Faint hairline rules mark the ticks;
the baseline is the strongest line.

### Field (`?history=field`)

Weeks run left to right with Mon–Sun columns and a date label per week
row. Each in-window day is a square; its fill has five discrete ink
levels by detection count, and its number sits centred in the square.
The number is white ink on the low levels and near-black ink on the
bright ones, like printed ink on paper. Today has a one-pixel ring.
Days outside the window have no square. The page never needs a legend:
a one-line caption says "Each square is a day; the number is that day's
detections."

Both layouts carry the window (`Last 30 days · 29 Oct – 27 Nov 2026`),
the species' common and scientific names, and `N of 30 days · total
detections`.

## Data

`GET /history.json?scientific_name=…` is fetched when the overlay opens.
It returns 30 calendar days in the configured timezone, oldest first,
with quiet days present as zeroes, plus each day's detection count and
first/last local times. It merges every model and applies the same
confidence and birds-only rules as today's list. Bucketing is done in
Python, because SQLite's `localtime` follows the process timezone, not
`TZ`.

## Behaviour

- Opening: the name is a threadbare button (no chrome); the tap never
  advances the carousel. `?open=<scientific name>` opens a species'
  history on load, for a shareable or reviewable URL.
- A **Bars · Calendar** switch at the foot of the placard flips the
  reading in place, without refetching. The active word is underlined and
  the address bar is updated, so a reload or a data-change reload stays
  on the chosen reading; an explicit `?history=` still wins, otherwise
  the last choice is kept in local storage.
- The veil is the species list's `rgba(0,0,0,0.72)` with a 14px blur.
- ← and → step to the previous/next bird while the history is open,
  swapping the photograph behind the veil and the history in the placard
  together. (The species list keeps the arrows for its own scrolling.)
- Closing: ✕, Escape, a tap outside the placard, or 45 s without
  interaction. The carousel resumes with a fresh full slide duration.
- A pending `/data.json` reload waits for the overlay to close.
- Keyboard users get focus on Close and back on the name; the name button
  carries `aria-expanded` and `aria-controls`.
- The page header and slide caption fade while the history is open.

## Left to the builder

Exact gutters, tick counts and transitions within the template's existing
scale. The chart is drawn in the page's inline script from the JSON; no
new dependencies or routes beyond `/history.json`.
