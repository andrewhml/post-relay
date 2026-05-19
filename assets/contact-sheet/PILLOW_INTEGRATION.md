# Pillow Render Spec — Post Relay Contact Sheet & Carousel Preview

> Hand this file to the engineering agent integrating these designs into the
> Python CLI + Discord-attachment pipeline. Every measurement, color, font,
> and drawing operation needed to reproduce the designs pixel-for-pixel is
> below. **The agent should NOT need to look at the React source or guess
> values — everything is specified here.**

---

## 1. What you are building

Three static PNG artifacts the agent posts as Discord attachments, one per
stage of the review workflow. Splitting selection from cropping keeps each
artifact lightweight to render and easy for the user to parse.

1. **Stage 01 — Contact Sheet (Select)** — every photo in the library with
   a single-letter sticker (A, B, C, …). No crop overlays, no chess grid,
   no metadata. The user picks photos by letter in chat.
2. **Stage 02 — Contact Sheet (Crop)** — same component, rendered with the
   **selected subset only**. Adds crop rectangle, 5×5 chess grid, LEAD
   designator, and per-photo ratio / anchor / tightness. The user nudges
   crops by chess coord in chat.
3. **Stage 03 — Carousel Preview** — the finalized post: selected photos in
   carousel order at the locked Instagram aspect ratio, with pagination
   dots and an optional caption preview.

All three render at **720 px wide**. Height varies with content.

A complete review session in chat:

```
agent  → [Stage 01 sheet — full library A..I]
user   → "keep E, C, B, G"
agent  → [Stage 02 sheet — E, C, B, G only; E as lead; crop tools on]
user   → "shift C to B2, tighten E"
agent  → [Stage 02 re-rendered with new anchors]
user   → "lgtm, 4:5"
agent  → [Stage 03 carousel at 4:5]
```

---

## 2. Visual identity — preserve exactly

### 2.1 Colors

| Token | Hex | Used for |
|---|---|---|
| `bg` | `#0c0b09` | Page background outside the sheet |
| `paper` | `#14120f` | Sheet & carousel background (the dark card) |
| `paper_soft` | `#1a1814` | kbd chip fill (footer hint) |
| `mat` | `#0c0b09` | Letterbox bars behind photos in cells |
| `text` | `#ece8de` | Title, primary text on dark |
| `text_soft` | `#b8b3a7` | Secondary text, metadata values |
| `mute` | `#807a6e` | Eyebrow, footer text, captions label |
| `mute_soft` | `#5d584f` | "·" separators, inactive dots |
| `line` | `#1c1a16` | Header/footer borders (alpha 0.07 over paper, baked) |
| `line_strong` | `#2a2722` | kbd chip border (alpha 0.15 over paper, baked) |
| `crop_line` | `#f0eee8` | Crop rectangle outline (alpha 0.94 over photo, baked) |
| `crop_scrim_rgba` | `(6,5,4,140)` | Scrim outside crop (45% alpha) |
| `accent` | `#e8a838` | Amber — stickers, active grid cell, LEAD pin, dots |
| `accent_fg` | `#1a1714` | Text on amber background |
| `accent_soft_rgba` | `(232,168,56,107)` | Active grid cell fill (42% alpha) |
| `accent_in_crop_rgba` | `(232,168,56,26)` | Grid cells the crop overlaps (10% alpha) |

When the spec says "alpha 0.42", you have two options in Pillow:

- **Composite mode**: build an RGBA layer with that alpha, then
  `Image.alpha_composite()` onto the base. Required for grid cells that
  overlay the photo.
- **Pre-mixed**: blend the RGB against the known background once and use the
  resulting opaque hex. Cheaper but only works on flat backgrounds.

The crop rectangle uses **transparency over the photo** so both color and
alpha are needed; you must use the composite path.

### 2.2 Type

Download two font families before rendering. Both are SIL Open Font License
and freely redistributable:

- **IBM Plex Sans** — Regular (400), Medium (500), SemiBold (600)
- **IBM Plex Mono** — Regular (400), Medium (500), SemiBold (600)

Place the `.ttf` files alongside the renderer (e.g. `fonts/IBMPlexMono-SemiBold.ttf`).

| Role | Family | Size (px) | Weight | Tracking |
|---|---|---|---|---|
| Eyebrow | Mono | 9.5 | 400 | letter-spacing 0.18em → +1.7px between chars |
| Title | Sans | 17 | 500 | letter-spacing -0.005em ≈ 0 |
| Sub (header right) | Mono | 10 | 400 | letter-spacing 0.14em → +1.4px |
| Photo sticker (A, B, …) | Mono | 11.5 | 600 | letter-spacing 0.04em → +0.5px |
| LEAD pin | Mono | 9.5 | 600 | letter-spacing 0.16em → +1.5px |
| Grid cell label | Mono | 8.5 | 500 | letter-spacing 0.04em → +0.3px |
| Active grid cell label | Mono | 10 | 600 | letter-spacing 0.04em → +0.4px |
| Filename in meta | Mono | 11 | 400 | letter-spacing 0.005em ≈ 0 |
| Meta attrs (ratio, anchor, tightness) | Mono | 10 | 400/500 | letter-spacing 0.06em → +0.6px |
| LEAD label in meta | Mono | 8.5 | 600 | letter-spacing 0.16em → +1.4px |
| Anchor coord value (◎ C3) | Mono | 10 | 500 | letter-spacing 0.08em → +0.8px, color = accent |
| Footer text | Mono | 10.5 | 400 | letter-spacing 0.02em ≈ 0 |
| Footer kbd | Mono | 9.5 | 400 | letter-spacing 0.02em ≈ 0 |
| Carousel position chip (1/4) | Mono | 10 | 600 (num) / 400 (rest) | 0.04em |
| Carousel slide num (#01) | Mono | 10 | 500 | 0.08em, color = accent |
| Carousel slide filename | Mono | 10 | 400 | 0.04em, color = mute |
| Caption label | Mono | 9.5 | 400 | 0.14em, uppercase |
| Caption body | Sans | 12 | 400 | 0, line-height 1.5 → leading 18 |

Pillow has no native letter-spacing. Render character-by-character: measure
each glyph with `font.getbbox(ch)[2]`, advance by that plus the extra px.
Exception: for body sentences (filenames, captions) the spacing is small
enough that drawing the whole string with `draw.text` looks the same.

All eyebrow / sub / LEAD / "Crop talk" / meta attrs text is UPPERCASE —
convert via `s.upper()` before drawing.

### 2.3 Stroke and corner radii

- All horizontal dividers (header border, footer border): **1px**, color `line`
- Crop rectangle outline: **1.5px** rounded to 2px in Pillow, color `crop_line`
- Grid cell border: **1px**, color `(255,255,255,13)` (5% alpha — barely visible)
- Active grid cell extra border: **1px**, color `accent`, drawn on top
- Photo sticker corner radius: **3px**
- LEAD pin corner radius: **2px**
- kbd corner radius: **3px**
- Position chip corner radius: **3px**

Pillow's `rounded_rectangle` (Pillow ≥9.4) handles rounded corners cleanly.

---

## 3. Data shapes (input)

### 3.1 Photo

```python
photo = {
    "n":     1,                  # int, 1-indexed display number
    "file":  "IMG_4821.jpg",     # str, original filename
    "src":   "/path/to/file.jpg",# local path (Pillow opens locally)
    "w":     4032,               # int, native pixel width
    "h":     3024,               # int, native pixel height
    "ratio": 1.0,                # float, agent-recommended IG crop ratio
    "ax":    0.10,               # float 0..1, crop anchor X
    "ay":    0.20,               # float 0..1, crop anchor Y
    "tight": 1.00,               # float 0..1, crop scale (1 = max fit)
}
```

### 3.2 Contact Sheet inputs

```python
ContactSheetInputs = {
    "mode":     str,             # 'select' (stage 01) or 'crop' (stage 02)
    "photos":   list[photo],     # for 'select': full library
                                 # for 'crop':  selected subset, in carousel order
    "lead_n":   int | None,      # n of the lead photo (crop mode only; None in select)
    "title":    str,             # "Granary Coffee · feed candidates"
    "sub":      str,             # "shoot 02 · nov 18"  (UPPERCASED on render)
}
```

### 3.3 Carousel Preview inputs

```python
CarouselInputs = {
    "photos":  list[photo],      # full library — slides look up by n
    "order":   list[int],        # photo n's in carousel order; order[0] = lead
    "ratio":   float,            # locked IG ratio for ALL slides
    "caption": str | None,       # optional caption preview text
}
```

The lead **on the carousel is always the first slide** (`order[0]`). The
lead **on the contact sheet** is `lead_n` (may differ if the agent is still
proposing).

### 3.4 The crop math drives most rendering

Use `crop_helpers.py` (shipped alongside this doc). Every box you draw on a
photo is `cropBox(photo)` or `cropBox(photo, carousel_ratio)`. Every chess
coord is `chess_from_anchor(photo["ax"], photo["ay"])`. Every label is
`label_from_index(photo["n"])`. **Do not reimplement these.**

---

## 4. Master canvas — Contact Sheet

### 4.1 Dimensions

- **Width**: 720 px (fixed)
- **Height**: header (88) + body + footer (44)
- Header height = 20 (top pad) + eyebrow line (~15 with baseline) + 6 (gap) +
  title line (~24) + 16 (bottom pad) + 1 (border) = **88 px**
- Footer height = 12 (top pad) + ~16 (content) + 12 (bottom pad) + 1 (border) =
  **44 px** — but the border is at top so it's actually 1 + 40 = 41; round to 44
- Body height = (rows) × (cell + 56 meta) + (rows − 1) × 18 vertical gap + 18 top pad + 14 bottom pad
- For 9 photos in 3 columns × 3 rows: 3 × (223 + 56) + 2 × 18 + 18 + 14 = **905 px**

Total for the 9-photo sheet: **88 + 905 + 44 = 1037 px** tall.

Fill the entire canvas with `paper` (#14120f).

### 4.2 Header

Anchor (0,0) is top-left of the sheet.

| Element | Top | Left | Right | Notes |
|---|---|---|---|---|
| Eyebrow row | 20 | 24 | (varies) | Single line, never wraps |
| Eyebrow item: "CONTACT SHEET" | 20 | 24 | — | mute color |
| Eyebrow dot (•) | 20+vertical-center | after item + 8px gap | — | 3×3 px circle, mute_soft |
| Eyebrow item: "09 PHOTOS" | (same baseline) | 8px after dot | — | `f"{count:02d} PHOTOS"` |
| Eyebrow dot | | 8px after | — | |
| Eyebrow item: "A1–E5 GRID" | | 8px after | — | **color = accent**, the variant accent |
| Title | ~20+15+6 = 41 | 24 | — | 17px Sans Medium, color text |
| Sub | (right-aligned, baseline aligned with title) | — | 24 | 10px Mono, color mute, uppercase |
| Border bottom | 87 | 0 | 720 | 1px line color |

Use `draw.line` for the border. Use baseline alignment when placing the
title and sub on the same row — measure each font's ascent and align.

### 4.3 Body — photo card grid

Body region: y = 88 to y = 88 + body_height. Padding inside: 18 top, 16
sides, 14 bottom. So usable region for the grid: x = 16 to x = 704
(688 wide), y starting at 88 + 18 = 106.

3 columns with 10px horizontal gap → each column = (688 − 20) / 3 = **222.67
≈ 223 px wide**. Use 223 for cols 0 and 1, 222 for col 2 (or distribute the
remainder; the human eye won't notice 1px).

Vertical gap between rows: **18 px** (this is the gap that includes the
56px meta strip).

Each card stacks:
- **Cell**: 223 × 223 (square, 1:1 aspect)
- **Meta strip**: 223 wide × ~56 tall, immediately below the cell

So total card height ≈ 279 px. Row gap is the 18px above; cards inside a row
are flush with each other vertically at the cell top.

### 4.4 Per-card render — Cell (223×223)

The cell is a dark mat with the photo letterboxed inside.

Steps (in order):

1. Fill cell with `mat` (#0c0b09).
2. **Compute photo display size:** scale the source image so it fits the 223×223
   box at its native aspect. If photo is landscape (w > h), display width =
   223, display height = 223 × h/w. If portrait, height = 223, width =
   223 × w/h.
3. **Center the photo** inside the cell:
   - photo_x = cell_x + (223 - display_w) // 2
   - photo_y = cell_y + (223 - display_h) // 2
4. Load the source, scale it (`PIL.Image.thumbnail` or `resize`), paste it
   at (photo_x, photo_y).

**STAGE 01 (`mode == 'select'`)** stop here — skip steps 5–9. Then jump to
step 10 (sticker). Skip steps 11 (LEAD pin) and 12 (lead glow): lead is
only designated in the crop stage.

The stage 01 cell is therefore: mat fill + photo + amber sticker. Nothing
else. The user just sees the library to pick from.

**STAGE 02 (`mode == 'crop'`)** continue with steps 5–12:

5. Compute the crop box: `box = crop_box(photo)` → `(x, y, w, h)` normalised.
6. Convert to pixel coords **relative to the photo area** (not the cell):
   - crop_px_x = photo_x + box.x × display_w
   - crop_px_y = photo_y + box.y × display_h
   - crop_px_w = box.w × display_w
   - crop_px_h = box.h × display_h

7. **Draw the scrim** (everything outside the crop, dimmed):
   - Create an RGBA overlay layer the same size as the photo area
   - Fill it with `crop_scrim_rgba` = (6, 5, 4, 140)
   - "Cut out" the crop rectangle by filling it with (0,0,0,0)
   - Alpha-composite the overlay onto the cell at (photo_x, photo_y)

8. **Draw the crop rectangle outline**: 1.5px (use 2 in Pillow with antialiasing,
   or draw two 1px lines offset) in `crop_line` color, at the crop rect bounds.

9. **Draw the 5×5 grid overlay** (over the crop scrim + photo):
   - Cell size: photo_area_w / 5 by photo_area_h / 5
   - For each (col, row) in [0..4]×[0..4]:
     - cell_left = photo_x + col × (display_w / 5)
     - cell_top  = photo_y + row × (display_h / 5)
     - Determine state:
       - `is_active` if `chess_from_anchor(ax, ay) == col_letter + row_str`
       - `is_in_crop` if (col, row) is inside `chess_span(box)` rectangle
       - else inactive
     - Draw 1px border around the cell in (255,255,255,13) — very faint
     - If `is_in_crop` (not active): fill the cell interior with `accent_in_crop_rgba` (232,168,56,26)
     - If `is_active`: fill with `accent_soft_rgba` (232,168,56,107) AND
       draw a 1px `accent` border on top
     - Draw the coord label (e.g. "C3") centered in the cell:
       - 8.5px Mono Medium for inactive, 10px Mono SemiBold for active
       - color: inactive = (255,255,255,87); in-crop = (255,255,255,128);
         active = `text` (#ece8de) with text shadow rgba(0,0,0,0.6) at offset (0,1)
   - The active cell highlight is **semi-transparent** — the photo must
     remain visible through it. Do not use opaque amber.

10. **Draw the photo sticker** (the letter label, e.g. "A"):
    - Position: top-left of the cell, 8px inset from cell edges
    - Box: 30 wide × 24 tall (min-width 30; if the letter is 1 char it's 30
      wide; if A–Z it's always 1 char so 30 is correct)
    - Fill: `accent` (#e8a838), rounded 3px
    - Inner highlight: 1px line `(255,255,255,46)` on the top edge
    - Inner shadow: 1px line `(0,0,0,31)` on the bottom edge
    - Drop shadow: 2px offset (0, 2), blur 6, color `(0,0,0,89)` — under
      the sticker, before drawing the sticker itself
    - Text: `label_from_index(photo["n"])` (single uppercase letter),
      11.5px Mono SemiBold, color `accent_fg` (#1a1714), centered in the box.
      Add ~0.5px letter-spacing for multi-char (not needed for single letter).

11. **If `photo["n"] == lead_n`**, draw the LEAD pin:
    - Position: top-right of the cell, 8px inset from cell edges
    - Box: height 18, padding 0 left/right 7 → measure "LEAD" with 0.16em
      spacing, total inner width ≈ 32, so box ≈ 32 + 14 = 46 wide.
      Actually measure precisely with the font; the box hugs the text + 7px
      padding each side.
    - Border: 1px `accent`, rounded 2px
    - Fill: transparent (no fill)
    - Text: "LEAD" uppercase, 9.5px Mono SemiBold, color `accent`, vertically
      centered. Letter-spacing 0.16em — draw char-by-char.

12. **Also draw the cell box-shadow** (the lead glow):
    - If `is_lead`: inset 1.5px `accent` border on the cell itself (drawn
      before steps 10–11 so the sticker sits on top).
    - This is a hairline glow around the cell to mark the lead.

### 4.5 Per-card render — Meta strip (223 × 56)

The meta strip sits directly below the cell. It has 10px top padding and
2px bottom padding.

**STAGE 01 (`mode == 'select'`)** — single row, filename only:

Draw `photo["file"]`, 11px Mono Regular, color `text` (#ece8de). Truncate
with `…` if it would overflow the card width. Skip the attrs row entirely.

**STAGE 02 (`mode == 'crop'`)** — both rows:

```
y = cell_bottom + 10  ─────────────────────────────────
                       row 1: filename ............. LEAD (if lead)
y += ~13 (11px line)
                       row 2: ratio · ◎ coord · tightness
                       ───────────────────────────────
```

**Row 1 — file row** (single line, baseline at y_row1):

- Left: `photo["file"]` (e.g. "IMG_4821.jpg"), 11px Mono Regular.
  Color: `text` (#ece8de) normally; `accent` (#e8a838) if this is the lead photo.
  If width overflows the available space minus the LEAD label width minus
  6 (gap), truncate with `…` (measure & loop).
- Right: only if lead — "▲ LEAD" (the ▲ is U+25B2 BLACK UP-POINTING TRIANGLE),
  8.5px Mono SemiBold, color `accent`, uppercase, letter-spacing 0.16em.
  Right-aligned at column right edge (x = card_right - 2 padding).

**Row 2 — attrs row** (single line, ~9px below row 1):

Render in order, with `·` separators (6px gap on each side of the dot):

1. ratio text — `ratio_label(photo["ratio"])` (e.g. "1:1"), 10px Mono Regular,
   color `text_soft`, uppercase (the label is already in canonical form).
2. `·` separator, color `mute_soft`
3. `"◎ " + chess_from_anchor(...)` — the ◎ is U+25CE BULLSEYE.
   Render the ◎ at 10px and the coord ("C3") at 10px Mono Medium with
   0.08em spacing, both in `accent` color. (The whole thing is the
   "anchor pill" — same color throughout.)
4. `·` separator
5. tightness text — `tightness_label(photo["tight"])` (e.g. "WIDE"),
   10px Mono Regular uppercase, color `text_soft`.

All baseline-aligned. Letter-spacing 0.06em on the ratio + tightness words;
0.08em on the coord; the separators sit on the same baseline with their own
small letter-spacing.

### 4.6 Footer

Below the last row of cards, the body's 14px bottom padding ends. Then a
1px line in `line` color spans the full width (x=0 to x=720). Below that,
the footer content.

| Element | Top (relative to footer top) | Left | Notes |
|---|---|---|---|
| 1px border | 0 | 0 | line color, span to 720 |
| "CROP TALK" label | 12 (top pad) | 24 | 10.5px Mono Regular uppercase, color `text_soft`, letter-spacing 0.14em |
| First kbd: "shift 03 to B2" | 12 | (after label + 10 gap) | (see kbd spec below) |
| Subsequent kbds | same | 10px gap between each | |

**kbd chip** (one for each command example):
- Padding: 2 top, 6 right, 1 bottom, 6 left
- Background: `paper_soft` (#1a1814) (no, that's lighter than paper — yes; if
  it's invisible, you mixed up the layering — re-check colors)
- Border: 1px `line_strong` (#2a2722), rounded 3px
- Text: 9.5px Mono Regular, color `text_soft`, letter-spacing 0.02em

Footer content depends on mode:

```
Stage 01 (mode == 'select'):
REPLY       [keep A, C, D, G]   [drop F]   [include B too]

Stage 02 (mode == 'crop'):
CROP TALK   [shift C to B2]   [span D across A2–C4]   [tighten F]   [lead C]
```

These are static instructional hints — not generated from photo data. In
`select` mode the label is **REPLY** (uppercase, tracked); in `crop` mode
it's **CROP TALK**.

---

## 5. Master canvas — Carousel Preview

### 5.1 Dimensions

- Width: **720 px**
- Header: same structure as contact sheet, height **88 px**
- Body: 22 top pad + slide height + 8 bottom pad
  - Slide width: (720 − 48 sides − 36 gaps) / 4 = **159 px** (for 4 slides);
    formula for N slides: `(720 − 48 − (N−1) × 12) / N`
  - Slide height = slide_width / `ratio` (e.g. 159 / 0.8 = 199 px)
  - Plus slide meta (~28 px): 8 top pad + 10 text + 2 bottom pad
  - Total body = 22 + slide_height + 28 + 8 = **22 + 199 + 36 = 257 px** (for 4:5)
- Dots: 6 top + 5 dot + 18 bottom = **29 px**
- Caption (if present): 1 (border) + 14 + ~36 text (1.5 line-height × 12px × ~2 lines) + 20 = **~71 px**

Total for 4-slide 4:5 carousel with caption: 88 + 257 + 29 + 71 = **~445 px** tall.

### 5.2 Header

Same as contact sheet but eyebrow content is different:

```
CAROUSEL PREVIEW · 04 SLIDES · 4:5
Final post · ordered                          LEAD 05
```

- Eyebrow items: "CAROUSEL PREVIEW", "04 SLIDES" (`f"{n:02d} SLIDES"`),
  ratio_label uppercase — last item color is `accent`.
- Title: "Final post · ordered" — 17px Sans Medium.
- Sub right: "LEAD " + `label_from_index(order[0])` —
  the "LEAD " is mute color, the letter is `accent` SemiBold.

### 5.3 Slides

Slides are placed in a row, left-to-right, in `order` sequence. Spacing:

- First slide at x = 24
- Each next slide at: prev_x + slide_w + 12

For each slide:

1. **Compute the crop at the carousel ratio** (overrides photo's recommended ratio):
   `box = crop_box(photo, override_ratio=ratio)`

2. **Render the crop into the slide frame** (slide_w × slide_h):
   - The slide frame is dimensions `slide_w × (slide_w / ratio)`.
   - Open the source photo. Scale it so the cropped region exactly fills
     the frame:
     - display_w = slide_w / box.w
     - display_h = (slide_w / ratio) / box.h
     - These produce the same image aspect as `photo["w"]/photo["h"]`.
   - Compute the photo's display origin (top-left, in slide-local coords):
     - offset_x = -box.x × display_w
     - offset_y = -box.y × display_h
   - Resize the source to (display_w, display_h), then **crop** that down
     to the slide frame: `resized.crop((-offset_x, -offset_y, -offset_x +
     slide_w, -offset_y + slide_h))`.
   - Paste the result at the slide's frame position.

3. **Mat fill behind the photo**: fill the frame with `mat` first (#0c0b09)
   so any edge bleed is invisible.

4. **If lead (i == 0)**: draw an inset 1.5px `accent` border around the
   frame. The border is INSIDE the frame, drawn last.

5. **Lead pin** (only if i == 0):
   - Position: top-left of slide frame, 6px inset
   - Box: height 18, padding 0 left/right 6, fits "LEAD"
   - Fill: `accent` (#e8a838), rounded 2px
   - Text: "LEAD" 9.5px Mono SemiBold, color `accent_fg`, 0.16em spacing

6. **Position chip**:
   - Position: bottom-right of slide frame, 6px inset
   - Box: padding 3 top, 6 right, 3 bottom, 6 left
   - Fill: rgba(8,6,4,166) (65% alpha) — composite mode required
   - Border: 1px rgba(255,255,255,41) (16% alpha)
   - Corner radius: 3px
   - Text: render three glyphs with 0.04em spacing:
     - position number: SemiBold, color `text` (#ece8de)
     - "/" separator (1px left margin): Regular, color `text_soft`
     - total: Regular, color `text_soft`
   - 10px Mono, all glyphs baseline-aligned

### 5.4 Slide meta (below frame, full slide width)

- y starts at frame_bottom + 8 (top padding)
- Single line: `#` + label + " " + filename (truncate with … if too long)
  - "#" prefix + label (e.g. "#A"): 10px Mono Medium, color `accent`, 0.08em
  - filename: 10px Mono Regular, color `mute`, 0.04em, single line ellipsis

Note: the React component renders this as `#` + `String(photo.n).padStart(2,'0')`
(e.g. `#01`). **Switch this to `#` + `label_from_index(photo["n"])`** (e.g. `#A`)
to match the new letter convention. Same change applies anywhere `#NN` appears.

### 5.5 Pagination dots

- Horizontal row, centered, total width = (N−1) × 4 + active_w + (N−1) × 5
  Simpler: center the row in 720px.
- Each non-active dot: 5×5 px circle, `mute_soft` (#5d584f)
- The active (first) dot: 18×5 px rounded rect (radius 2.5), `accent`
- Gap between pips: 4px
- Top padding 6, bottom padding 18

### 5.6 Caption (optional)

If `caption` is set:

- 1px border line (`line` color) at top
- y_start = border + 14
- Left column: "CAPTION" label, 9.5px Mono Regular, color `mute`, 0.14em,
  uppercase. Right-aligned to col width ~70px (give or take).
- Right column: caption body, 12px Sans Regular, color `text_soft`, line
  height 18px. Wraps at column width (~720 − 24 − 70 − 12 gap − 24 = 590 px).
- Use Pillow's `textwrap` to wrap, then draw line-by-line.

---

## 6. Putting it together — module skeleton

```
post_relay/
  rendering/
    crop_helpers.py            # ← shipped with this doc
    fonts/
      IBMPlexSans-Regular.ttf
      IBMPlexSans-Medium.ttf
      IBMPlexSans-SemiBold.ttf
      IBMPlexMono-Regular.ttf
      IBMPlexMono-Medium.ttf
      IBMPlexMono-SemiBold.ttf
    palette.py                 # named colors from §2.1
    typography.py              # font loader, letter-spaced text drawer
    primitives.py              # rounded_rect, scrim, label, kbd
    contact_sheet.py           # render_contact_sheet(inputs) → PIL.Image
    carousel_preview.py        # render_carousel_preview(inputs) → PIL.Image
```

Recommended top-level interface:

    photo["src"], file, w, h, ratio, ax, ay, tight       (unchanged)

The Python signature mirrors the JS:

```python
def render_contact_sheet(
    photos: list[dict],
    mode: str,                   # 'select' or 'crop'
    title: str,
    sub: str,
    lead_n: int | None = None,   # crop mode only; pass None in select mode
) -> Image.Image:
    """Returns an RGBA PIL Image, 720 wide, height computed from content."""
    ...

def render_carousel_preview(
    photos: list[dict],
    order: list[int],
    ratio: float,
    caption: str | None = None,
) -> Image.Image:
    ...
```

After rendering, save to a temporary path and attach to the Discord message:

```python
img = render_contact_sheet(photos, lead_n=3, title="…", sub="…")
img = img.convert("RGB")  # JPEG can't do alpha
buf = io.BytesIO()
img.save(buf, "PNG", optimize=True)
buf.seek(0)
await channel.send(file=discord.File(buf, filename="contact-sheet.png"))
```

PNG is better than JPEG here — the design has flat colors and sharp text,
so PNG compresses well and stays crisp. Expect ~150–250 KB per artifact.

---

## 7. Letter-spaced text drawing

Pillow doesn't ship letter-spacing. Use this helper:

```python
def draw_tracked(draw, xy, text, font, fill, tracking_em):
    """
    Draw `text` starting at `xy` with `tracking_em` extra spacing between
    characters (em = font size in px).
    """
    x, y = xy
    extra = font.size * tracking_em
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        # advance by glyph width + extra spacing
        bbox = font.getbbox(ch)
        glyph_w = bbox[2] - bbox[0]
        x += glyph_w + extra
    return x  # return final x so callers can chain

def measure_tracked(text, font, tracking_em):
    """Total width of letter-spaced text, in px."""
    extra = font.size * tracking_em
    total = 0
    for ch in text:
        bbox = font.getbbox(ch)
        total += (bbox[2] - bbox[0]) + extra
    return max(0, total - extra)  # no trailing space after last char
```

Use this for every uppercase/tracked label. For body sentences (filenames,
caption text), use plain `draw.text` — it looks identical at small tracking
values.

---

## 8. The chess-grid vocabulary

Cells in the 5×5 grid are addressed as letter+digit (A1..E5) where:

- A = column 0 (leftmost), E = column 4 (rightmost)
- 1 = row 0 (top), 5 = row 4 (bottom)
- C3 = dead center

The agent should teach the user this vocabulary. Both the **anchor** (where
the crop leans) and the **span** (which cells the crop overlaps) live in
the same coordinate space.

Sample chat patterns the agent should recognise and emit:

| User says | Agent action |
|---|---|
| `keep A, C, D, G` | Set the selection in this order; A becomes the lead |
| `lead C` | Set lead_n to that photo's n; carousel order may reshuffle |
| `drop F` | Remove from selection |
| `shift C to B2` | Update ax/ay to (0.25, 0.25), then re-emit the sheet |
| `center C` | Set ax=0.5, ay=0.5 (→ C3) |
| `nudge C left` | Decrement column by 1 step (subtract 0.25 from ax, clamp) |
| `tighten F` | tight -= 0.15 (clamp at 0.5) |
| `loosen F` | tight += 0.15 (clamp at 1.0) |
| `set carousel to 4:5` | ratio = 0.8 |

Tightness step ≈ 0.15 maps the snug / medium / wide bands cleanly.

---

## 9. Pixel parity — testing

To verify your render matches the design, generate a sheet with the sample
data shipped in `sample-data.js`, then diff against the standalone HTML
reference (open it in Chrome and screenshot the rendered region at 1×).

Critical checks:

- Background is `#14120f` (not pure black). Sample any non-element pixel.
- Photo sticker is amber-on-dark, top-left of every cell, letter only
  (A..I for the sample set), not "01..09".
- Active grid cell is **semi-transparent amber** — the photo must remain
  visible through it. If it's opaque, you used the wrong color value.
- LEAD pin is amber outline (not filled) on the contact sheet; amber FILLED
  on the carousel.
- Pagination dots: first dot is an elongated amber pill, others are small
  gray circles.

---

## 10. What NOT to do

- **Don't render to JPEG.** The hairline borders, single-pixel text, and
  flat amber tend to introduce ringing. PNG is correct.
- **Don't substitute a system font.** IBM Plex's geometry is part of the
  visual identity. Bundle the .ttf files and load with explicit paths.
- **Don't add an emoji or 📍-style icon.** The design uses two unicode
  glyphs only (◎ U+25CE bullseye, ▲ U+25B2 triangle); render them in the
  same Mono font as adjacent text.
- **Don't open-render at higher resolution and downscale.** The design is
  authored at 1× / 720 wide. If you want a Retina PNG, render at 2× by
  multiplying every dimension and font size by 2 — but keep the math
  symmetric. Don't render at 1× then upscale (blurry) or 3× then downscale
  (subpixel artifacts).
- **Don't reformat the photo data.** Cropping is deterministic on `ratio`,
  `ax`, `ay`, `tight`. The agent emits these and the renderer uses them
  unchanged.
