# Post Relay · Contact Sheet & Carousel Preview

Two React components for the photo-review flow:

- `<ContactSheet>` — displays the agent's photo candidates with numbered
  callouts, a 5×5 chess-grid crop reference (A1–E5), and a designated lead
  photo. Used by the agent to deliver review options in chat.
- `<CarouselPreview>` — renders the finalized post: selected photos in
  carousel order, cropped to a single locked Instagram aspect ratio, with
  the lead slide marked and pagination dots.

## Files

| File | Purpose |
|---|---|
| `contact-sheet.jsx` | `<ContactSheet>` component (React) |
| `carousel-preview.jsx` | `<CarouselPreview>` component (React) |
| `crop-helpers.js` | Pure crop math — no dependencies, drop into any project |
| `sample-data.js` | Sample photo objects showing the expected data shape |
| `contact-sheet-final.css` | All component styles (warm-dark · amber accent) |
| `Contact Sheet Final.html` | Standalone demo wiring both components together |

## Photo data shape

```js
{
  n:     1,                 // display number (01..NN)
  file:  'IMG_4821.jpg',    // original filename
  src:   'https://…',       // image URL (your CDN / blob)
  w:     4032,              // native width
  h:     3024,              // native height
  ratio: 1,                 // agent-recommended IG crop ratio (1, 0.8, 1.91, …)
  ax:    0.10,              // crop anchor X (0..1) — where the crop "leans"
  ay:    0.20,              // crop anchor Y (0..1)
  tight: 1.00,              // crop scale (1 = max fit; < 1 = tighter framing)
}
```

## Usage

```jsx
<ContactSheet
  photos={photos}
  leadNum={5}                                    // optional — designates the lead
  title="Granary Coffee · feed candidates"
  sub="shoot 02 · nov 18"
/>

<CarouselPreview
  photos={photos}                                // full library (lookups by n)
  order={[5, 3, 2, 7]}                           // n's in carousel order
  ratio={0.8}                                    // 4:5 — locks all slides to one shape
  caption="Saturday mornings at the Granary…"    // optional
/>
```

## Crop talk vocabulary

The chess grid (`A1`–`E5`) gives 25 named anchor positions for chat:

- `shift 03 to B2` — move photo 03's crop to top-left-ish
- `center 05` — anchor to `C3`
- `span 04 across A2–C4` — explicit cell span
- `tighten 06` / `loosen 09` — adjust the crop scale
- `lead 03` — designate photo 03 as the cover

## Integration notes

- Components are scope-isolated by class prefix (`cs-*`, `cp-*`).
- Crop math (`crop-helpers.js`) is plain ES with no React dependency —
  reuse server-side or in other UI.
- The CSS uses `:root` custom properties prefixed `--cs-*`; override these
  to match your design tokens.
- Components expect plain `<img src>` URLs. Swap `picsum.photos` in
  `sample-data.js` with your storage URLs.

## Running the demo

Serve the folder over HTTP (`python -m http.server`, etc.) and open
`Contact Sheet Final.html`. Or open directly in a browser — the unpkg
React/Babel imports work file:// in modern Chrome.
