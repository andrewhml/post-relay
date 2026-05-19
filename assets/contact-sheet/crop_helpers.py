# =========================================================================
# crop_helpers.py — Pure-Python port of crop math for Post Relay.
# No dependencies. Drop into any Python project.
# =========================================================================
"""
Compute Instagram crops from a photo + anchor + tightness.

Glossary
--------
ratio       crop aspect ratio = crop_w / crop_h
            1.0   = 1:1 square
            0.8   = 4:5 portrait
            1.91  = 1.91:1 landscape
            0.5625 = 9:16 stories/reels

ax, ay      crop anchor (0.0–1.0). Where the crop "leans" within the image.
            0,0 = top-left; 0.5,0.5 = center; 1,1 = bottom-right.

tight       crop scale (0.0–1.0). 1.0 = the largest crop that fits the
            ratio; lower = a smaller (tighter) crop inside that.

box         crop rectangle in image-normalised coords: x, y, w, h ∈ [0,1].
"""

from dataclasses import dataclass


@dataclass
class CropBox:
    x: float
    y: float
    w: float
    h: float


def fit_crop(img_w: int, img_h: int, ratio: float,
             ax: float = 0.5, ay: float = 0.5) -> CropBox:
    """
    Largest rectangle of the given aspect ratio that fits inside an image,
    anchored toward (ax, ay).
    """
    img_aspect = img_w / img_h
    if ratio > img_aspect:
        cw, ch = 1.0, img_aspect / ratio
    else:
        cw, ch = ratio / img_aspect, 1.0
    return CropBox(
        x=(1 - cw) * ax,
        y=(1 - ch) * ay,
        w=cw,
        h=ch,
    )


def crop_box(photo: dict, override_ratio: float | None = None) -> CropBox:
    """
    Final crop box for a photo, with tightness applied. Pass override_ratio
    when locking a whole carousel to one ratio.

    `photo` must have keys: w, h, ratio, ax, ay; optional tight (default 1.0).
    """
    r = override_ratio if override_ratio is not None else photo["ratio"]
    base = fit_crop(photo["w"], photo["h"], r, photo["ax"], photo["ay"])
    t = photo.get("tight", 1.0)
    cw, ch = base.w * t, base.h * t
    return CropBox(
        x=(1 - cw) * photo["ax"],
        y=(1 - ch) * photo["ay"],
        w=cw,
        h=ch,
    )


def ratio_label(r: float) -> str:
    """Render a crop ratio as a human label."""
    if abs(r - 1)      < 0.01: return "1:1"
    if abs(r - 0.8)    < 0.01: return "4:5"
    if abs(r - 1.91)   < 0.02: return "1.91:1"
    if abs(r - 9 / 16) < 0.01: return "9:16"
    return f"{r:.2f}"


def chess_from_anchor(ax: float, ay: float) -> str:
    """
    5×5 chess-style coord (A1..E5) from anchor.
    A = left column, E = right column; 1 = top row, 5 = bottom row.
    """
    col = max(0, min(4, round(ax * 4)))
    row = max(0, min(4, round(ay * 4)))
    return chr(65 + col) + str(row + 1)


def chess_span(box: CropBox) -> tuple[int, int, int, int]:
    """
    Cells the crop overlaps in the 5×5 grid.
    Returns (c0, c1, r0, r1) — inclusive column and row indices, 0..4.
    """
    import math
    c0 = max(0, min(4, math.floor(box.x * 5)))
    c1 = max(0, min(4, math.ceil((box.x + box.w) * 5) - 1))
    r0 = max(0, min(4, math.floor(box.y * 5)))
    r1 = max(0, min(4, math.ceil((box.y + box.h) * 5) - 1))
    return c0, c1, r0, r1


def tightness_label(t: float) -> str:
    """Named tightness for a tight value in [0, 1]."""
    if t >= 0.95: return "wide"
    if t >= 0.83: return "medium"
    return "snug"


def label_from_index(n: int) -> str:
    """
    Photo letter label from 1-indexed display number.
    1 → "A", 2 → "B", … 26 → "Z".
    Used as the photo's stable reference in chat (e.g. "use C, B, A, G").
    """
    return chr(64 + n)
