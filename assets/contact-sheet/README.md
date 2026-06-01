# Post Relay · Contact Sheet & Carousel Preview

Two visual artifacts the agent posts as Discord attachments:

- **Contact Sheet** — lettered photo grid with crop overlays + chess-grid
  reference, used during review.
- **Carousel Preview** — selected photos in carousel order at the locked
  Instagram aspect ratio, used after confirmation.

## For the engineering agent integrating this

Read **`PILLOW_INTEGRATION.md`** — it specifies every measurement, color,
font, and drawing step needed to reproduce the design pixel-for-pixel in
Python + Pillow. No detail is left to interpretation.

Then port **`crop_helpers.py`** as-is (drop in any project).

## Files

| File | Purpose |
|---|---|
| `PILLOW_INTEGRATION.md` | Exhaustive render spec for Python + Pillow |
| `crop_helpers.py` | Pure-Python crop math (no deps) |
| `sample-data.js` | Sample photo data showing input shape |
| `Contact Sheet Final.html` | Browser-renderable visual reference |
| `reference/Contact Sheet Final — standalone.html` | Self-contained version (no external assets) |

The remaining files (`contact-sheet.jsx`, `carousel-preview.jsx`,
`contact-sheet-final.css`, `crop-helpers.js`) are the original React
implementation, kept as a visual reference. The Python renderer should
follow `PILLOW_INTEGRATION.md`, not these files.

## Photo data shape (input contract)

```python
photo = {
    "n":     1,                  # 1-indexed display number
    "file":  "IMG_4821.jpg",     # original filename
    "src":   "/path/to/file.jpg",# local image path (Pillow opens locally)
    "w":     4032,               # native pixel width
    "h":     3024,               # native pixel height
    "ratio": 1.0,                # agent-recommended IG crop ratio
                                 #   1.0 = 1:1, 0.8 = 4:5, 1.91 = 1.91:1
    "ax":    0.10,               # crop anchor X (0..1)
    "ay":    0.20,               # crop anchor Y (0..1)
    "tight": 1.00,               # crop scale (1 = max fit; < 1 = tighter)
}
```

Photos are referenced in chat by letter: photo `n=1` → "A", `n=2` → "B",
etc. (See `crop_helpers.label_from_index`.)

## Chat vocabulary (chess-grid)

Cells of a 5×5 grid overlaid on each photo are addressed as letter+digit
(A1..E5). C3 is dead center. The user adjusts crops with phrases like:

- `keep A, C, D, G` — selection + order; first is the lead
- `lead C` — designate the cover photo
- `shift C to B2` — change `ax`,`ay`
- `center D` — set to C3
- `tighten F` / `loosen F` — adjust `tight`
- `set carousel to 3:4` — change the locked carousel ratio to the current feed/profile default; use `4:5` only as an explicit compatibility override
