# Integration Prompt — Contact Sheet & Carousel Preview

> Hand this file (plus the rest of the `final/` folder) to the agent that
> will incorporate these designs into the application.

---

## What you're integrating

Two React components for **Post Relay**, a chat-driven app that helps users
review photo libraries and ship Instagram posts. The central interaction is
a conversation between the user and an AI agent — these components are the
visual artifacts the agent renders inside its chat messages.

1. **`<ContactSheet>`** — the agent posts this when it has a set of photo
   candidates for the user to review. The user replies in natural language
   referencing photo numbers and chess-grid coordinates (e.g.
   _"keep 5, 3, 2, 7 and shift 03 to B2"_).
2. **`<CarouselPreview>`** — the agent posts this once selection and order
   are confirmed, showing the finalized Instagram post in carousel order at
   the locked aspect ratio.

Both components are designed to render **inline inside a chat message** at
a maximum width of ~720px. They are not full-page UIs — drop them into
whatever chat message component renders agent output in your app.

---

## Files in this folder

| File | What it is | Loads as |
|---|---|---|
| `contact-sheet.jsx` | `<ContactSheet>` React component | JSX (Babel) |
| `carousel-preview.jsx` | `<CarouselPreview>` React component | JSX (Babel) |
| `crop-helpers.js` | Pure crop math — no React dep | Plain ES |
| `sample-data.js` | Sample photo objects (the data contract) | Plain ES |
| `contact-sheet-final.css` | All component styles | CSS |
| `Contact Sheet Final.html` | Standalone demo wiring both together | HTML |
| `README.md` | Public-facing usage notes | Markdown |

The components target **React 18**. If your app uses a build pipeline
(Vite / Next / CRA), convert the JSX files to ESM modules and import
helpers from `crop-helpers.js`. If your app loads scripts directly in HTML,
the existing `<script src>` setup in the demo works as-is.

---

## Visual identity — preserve this

The design is intentional. Do not redecorate without checking with the
product designer first.

- **Theme:** warm dark. Background `#14120f`, mat `#0c0b09`.
- **Accent:** `#e8a838` amber (chinagraph-pencil / film-slate reference).
  Used for: number stickers, the active chess-grid cell, lead designators,
  and the active carousel pagination dot. Don't introduce a second accent.
- **Type:** IBM Plex Sans + IBM Plex Mono. Filenames, numbers, coordinates,
  and any precise/technical text are always mono. Titles and prose are sans.
- **Number callouts** are amber chips with dark text — visible from across
  the room. Keep them prominent.
- **Filenames and crop metadata** live in a **strip below the photo, never
  overlaid on the image.** This was an explicit design decision.
- **Lead photo** is marked with both an amber outline on the cell and a
  `LEAD` pill in the meta strip. Carousel slides for the lead show a solid
  amber `LEAD` chip in the top-left of the slide frame.

CSS variables are declared on `:root` with the `--cs-*` prefix. To match
your existing design tokens, override these — don't rewrite the rules.

---

## Component APIs

### `<ContactSheet>`

```ts
type Props = {
  photos: Photo[];      // list of photo candidates
  leadNum?: number;     // `n` of the lead/cover photo (optional)
  title: string;        // sheet title, e.g. "Granary Coffee · feed candidates"
  sub: string;          // eyebrow subtitle, e.g. "shoot 02 · nov 18"
};
```

Renders a 3-column grid (chat-width). Each card shows:
- The photo letterboxed into a 1:1 cell on a dark mat
- A bright outlined rectangle showing the agent's recommended IG crop
- A 5×5 chess grid (`A1`..`E5`) with the active anchor cell amber-filled,
  and any other cells the crop overlaps faintly tinted
- An amber number sticker (`01`..`NN`) in the top-left
- A meta strip below with filename, ratio, anchor coord, and tightness

### `<CarouselPreview>`

```ts
type Props = {
  photos: Photo[];      // full library — lookups by `n`
  order: number[];      // `n` values in carousel order; order[0] is the lead
  ratio: number;        // single aspect ratio locked to the whole carousel
                        // 1 = 1:1, 0.8 = 4:5, 1.91 = 1.91:1
  caption?: string;     // optional caption preview shown below the slides
};
```

Renders horizontal slides (one per `order` entry) all cropped to `ratio`
using each photo's `ax`/`ay`/`tight`. Beneath the slides: IG-style
pagination dots (first dot elongated and amber to mark the lead), then the
caption.

---

## The data contract — `Photo`

```ts
type Photo = {
  n: number;        // display number, 1-indexed
  file: string;     // original filename, shown in meta strip
  src: string;      // image URL — your CDN / signed blob URL
  w: number;        // native pixel width
  h: number;        // native pixel height

  // The agent's recommended IG crop for THIS photo (the contact sheet
  // uses these to draw the bright crop rectangle and pick the active
  // chess-grid cell):
  ratio: number;    // crop ratio = cropW / cropH
                    //   1     = 1:1  square
                    //   0.8   = 4:5  portrait
                    //   1.91  = 1.91:1 landscape
                    //   9/16  = 9:16 stories/reels
  ax: number;       // anchor X (0..1) — where the crop "leans" horizontally
                    //   0 = leftmost, 0.5 = centered, 1 = rightmost
  ay: number;       // anchor Y (0..1) — same idea vertically
  tight: number;    // crop scale (1.0 = max fit; < 1.0 = tighter / more zoom)
};
```

`ax`/`ay`/`tight`/`ratio` are **the agent's outputs**, not user-input.
When the user says "shift 03 to B2", the agent translates that to new
`ax`/`ay` values and re-emits the contact sheet.

Quantization is handled inside the component (`chessFromAnchor()`):
`round(ax * 4)` → column, `round(ay * 4)` → row. So `ax=0.0,ay=0.0` → `A1`,
`ax=0.5,ay=0.5` → `C3`, `ax=1.0,ay=1.0` → `E5`.

---

## Crop math primer

`crop-helpers.js` is dependency-free and is the source of truth for crop
geometry. Reuse it server-side if you compute crops in the backend.

```js
fitCrop(imgW, imgH, ratio, ax, ay)
// → { x, y, w, h }   crop box in image-normalised (0..1) coordinates.
//   The largest rectangle of the given ratio that fits in the image,
//   anchored toward (ax, ay).

cropBox(photo, overrideRatio?)
// → { x, y, w, h }   final crop including `tight` scaling.
//   Pass overrideRatio when locking a whole carousel to one ratio.

chessFromAnchor(ax, ay)    // → "A1" .. "E5"
chessSpan(box)             // → { c0, c1, r0, r1 }  cells the crop covers
ratioLabel(r)              // → "1:1" | "4:5" | "1.91:1" | …
tightnessLabel(t)          // → "wide" | "medium" | "snug"
```

---

## Chess-grid vocabulary (for the chat agent)

The 5×5 grid gives you 25 named anchor positions. **Teach the AI agent to
both produce and understand this vocabulary** so the user and agent share a
language for cropping.

Columns: `A B C D E` (left → right). Rows: `1 2 3 4 5` (top → bottom).
`C3` is dead center.

User → agent inputs to recognise:

| Phrase | Effect on the referenced photo |
|---|---|
| `shift 03 to B2` | set `ax=0.25, ay=0.25` (column B = 0.25, row 2 = 0.25) |
| `center 05` | set `ax=0.5, ay=0.5` (C3) |
| `anchor 02 to top` | set `ay=0` (row 1) — keep `ax` |
| `nudge 04 left` | decrement column by 1 step (0.25) |
| `tighten 06` / `snug 06` | reduce `tight` one step (e.g. 1.0 → 0.85) |
| `loosen 09` / `wide 09` | increase `tight` one step |
| `lead 03` | set the lead/cover photo to n=3 |
| `keep 5, 3, 2, 7` | select those photos in that order |
| `drop 06` | remove photo 6 from selection |

Agent → user output: when the agent re-emits the contact sheet, include
the new anchor in plain English (_"Moved 03's crop to B2."_), and let the
visual artifact carry the rest.

---

## Integration steps

1. **Drop the files into your repo.** Suggested location:
   `src/components/contact-sheet/` (or wherever your other inline chat
   artifacts live).
2. **Wire the data.** Your agent emits photo arrays plus `leadNum`,
   `order`, and `ratio`. Persist these on the message — re-rendering the
   same message should produce the same artifact.
3. **Render inline in chat.** Wrap each component in your standard agent-
   message bubble. Don't let the bubble's padding shrink the components
   below ~640px — the 3-column grid and 4-slide row need the room.
4. **Match design tokens (optional).** Override the `--cs-*` CSS variables
   in your global theme so the amber matches your brand if needed.
5. **Replace sample image URLs.** `sample-data.js` uses `picsum.photos`
   placeholders. Use your actual photo storage URLs in production. The
   `src` must be a fully-cropped or original image — the components crop
   it visually via CSS, they don't request server-side crops.
6. **Hook up state.** Both components are presentational. Selection,
   reordering, and crop adjustment all happen via chat — your application
   state is whatever the agent emits. There's no internal state to manage.

---

## Things to wire up beyond drop-in

The components are intentionally minimal. Once they're rendering, you'll
likely want to add (in priority order):

1. **Photo zoom on click.** Currently passive. Hook clicks on `.cs-cell` /
   `.cp-slide-frame` to open a full-size lightbox.
2. **Selection / dropped states on the contact sheet.** Right now the
   sheet is purely display — once a user has said "use 5, 3, 2, 7", you
   may want to dim the non-selected photos and stamp `1st / 2nd / 3rd /
   4th` on the kept ones. Add a `selection?: { order: number[] }` prop and
   render a position chip + dimmed overlay accordingly.
3. **Image-loading skeletons.** Add a low-resolution placeholder or
   blur-up image while `<img>` resolves — the chess-grid overlay looks
   broken against an unloaded cell.
4. **A11y.** The cells should be focusable buttons if you wire click
   handling; the chess grid should be aria-hidden (decorative).

---

## What to leave alone

- **The crop math.** `fitCrop` / `cropBox` are exact. Don't substitute
  CSS `object-fit: cover` with `object-position: %` — it doesn't handle
  `tight` and accumulates rounding error on small frames.
- **The chess-grid quantisation.** `Math.round(ax * 4)` is what makes
  `ax=0.5 → C3` cleanly. Using `Math.floor` shifts everything off by half
  a cell.
- **Amber as the only accent.** A second accent (especially green/red
  selection states) will fight the design. If you need a selected state,
  use opacity / dim + a position chip, not a new color.
- **Overlaid filenames.** Filenames and ratio belong in the meta strip
  below the photo, not on it. This was an explicit design decision.

---

## Quick sanity check

After integrating, render with the sample data and verify:

- 9 photos in a 3-column grid with amber `01`..`09` stickers
- Photo `05` has an amber outline on its cell + a `LEAD` pill in its meta
- Each photo has exactly one amber-filled chess-grid cell (the active
  anchor); the cells the crop overlaps have a faint amber tint
- The carousel below shows 4 slides at 4:5 in the order `5, 3, 2, 7`
- The first carousel slide has a solid amber `LEAD` chip top-left
- Pagination dots: the first is an elongated amber pill, others are small
  gray dots

If any of those don't match, check the data — the components are
deterministic functions of their props.
