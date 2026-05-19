from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CropBox:
    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class ContactSheetPhoto:
    n: int
    file: str
    src: str
    w: int
    h: int
    ratio: float = 1.0
    ax: float = 0.5
    ay: float = 0.5
    tight: float = 1.0


CHESS_COLUMNS = "ABCDE"


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def fit_crop(img_w: int, img_h: int, ratio: float, ax: float = 0.5, ay: float = 0.5) -> CropBox:
    if img_w <= 0 or img_h <= 0:
        raise ValueError("Image dimensions must be positive")
    if ratio <= 0:
        raise ValueError("Crop ratio must be positive")
    img_aspect = img_w / img_h
    if ratio > img_aspect:
        cw = 1.0
        ch = img_aspect / ratio
    else:
        cw = ratio / img_aspect
        ch = 1.0
    return CropBox(x=(1 - cw) * clamp(ax), y=(1 - ch) * clamp(ay), w=cw, h=ch)


def crop_box(photo: ContactSheetPhoto, override_ratio: float | None = None) -> CropBox:
    ratio = override_ratio if override_ratio is not None else photo.ratio
    base = fit_crop(photo.w, photo.h, ratio, photo.ax, photo.ay)
    tight = clamp(photo.tight)
    cw = base.w * tight
    ch = base.h * tight
    return CropBox(x=(1 - cw) * clamp(photo.ax), y=(1 - ch) * clamp(photo.ay), w=cw, h=ch)


def chess_from_anchor(ax: float, ay: float) -> str:
    col = max(0, min(4, round(clamp(ax) * 4)))
    row = max(0, min(4, round(clamp(ay) * 4)))
    return f"{chr(65 + col)}{row + 1}"


def anchor_from_chess(anchor: str) -> tuple[float, float]:
    normalized = anchor.strip().upper()
    if len(normalized) != 2 or normalized[0] not in CHESS_COLUMNS or normalized[1] not in "12345":
        raise ValueError("Crop anchor must be A1 through E5")
    return CHESS_COLUMNS.index(normalized[0]) / 4, (int(normalized[1]) - 1) / 4


def chess_span(box: CropBox) -> dict[str, int]:
    import math

    c0 = max(0, min(4, math.floor(box.x * 5)))
    c1 = max(0, min(4, math.ceil((box.x + box.w) * 5) - 1))
    r0 = max(0, min(4, math.floor(box.y * 5)))
    r1 = max(0, min(4, math.ceil((box.y + box.h) * 5) - 1))
    return {"c0": c0, "c1": c1, "r0": r0, "r1": r1}


def ratio_label(ratio: float) -> str:
    if abs(ratio - 1) < 0.01:
        return "1:1"
    if abs(ratio - 0.8) < 0.01:
        return "4:5"
    if abs(ratio - 1.91) < 0.02:
        return "1.91:1"
    if abs(ratio - 9 / 16) < 0.01:
        return "9:16"
    return f"{ratio:.2f}"


def ratio_from_label(label: str) -> float:
    normalized = label.strip().lower()
    known = {"1:1": 1.0, "4:5": 0.8, "1.91:1": 1.91, "9:16": 9 / 16}
    if normalized in known:
        return known[normalized]
    if ":" in normalized:
        left, right = normalized.split(":", 1)
        return float(left) / float(right)
    return float(normalized)


def tightness_label(tight: float) -> str:
    if tight >= 0.95:
        return "wide"
    if tight >= 0.83:
        return "medium"
    return "snug"


def label_from_index(n: int) -> str:
    if n < 1 or n > 26:
        return str(n)
    return chr(64 + n)
