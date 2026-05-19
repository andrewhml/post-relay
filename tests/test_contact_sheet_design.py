from post_relay.contact_sheet_design import (
    ContactSheetPhoto,
    chess_from_anchor,
    chess_span,
    crop_box,
    fit_crop,
    ratio_label,
    tightness_label,
)


def test_fit_crop_returns_centered_square_for_landscape_image():
    box = fit_crop(4032, 3024, 1, 0.5, 0.5)

    assert box.x == 0.125
    assert box.y == 0
    assert box.w == 0.75
    assert box.h == 1


def test_crop_box_applies_override_ratio_and_tightness():
    photo = ContactSheetPhoto(
        n=3,
        file="IMG_0003.jpg",
        src="/photos/IMG_0003.jpg",
        w=4032,
        h=3024,
        ratio=1,
        ax=0.25,
        ay=0.75,
        tight=0.8,
    )

    box = crop_box(photo, override_ratio=0.8)

    assert round(box.x, 4) == 0.13
    assert round(box.y, 4) == 0.15
    assert round(box.w, 4) == 0.48
    assert round(box.h, 4) == 0.8


def test_chess_anchor_coordinates_match_design_quantization():
    assert chess_from_anchor(0.5, 0.5) == "C3"
    assert chess_from_anchor(0.0, 0.0) == "A1"
    assert chess_from_anchor(1.0, 1.0) == "E5"
    assert chess_from_anchor(0.25, 0.25) == "B2"


def test_chess_span_uses_floor_ceil_cells():
    box = fit_crop(4032, 3024, 1, 0.5, 0.5)

    assert chess_span(box) == {"c0": 0, "c1": 4, "r0": 0, "r1": 4}

    tighter = crop_box(
        ContactSheetPhoto(
            n=1,
            file="IMG_0001.jpg",
            src="/photos/IMG_0001.jpg",
            w=4032,
            h=3024,
            ratio=1,
            ax=0.5,
            ay=0.5,
            tight=0.5,
        )
    )
    assert chess_span(tighter) == {"c0": 1, "c1": 3, "r0": 1, "r1": 3}


def test_ratio_and_tightness_labels_match_design_contract():
    assert ratio_label(1) == "1:1"
    assert ratio_label(0.8) == "4:5"
    assert ratio_label(1.91) == "1.91:1"
    assert ratio_label(9 / 16) == "9:16"
    assert ratio_label(1.33) == "1.33"

    assert tightness_label(1.0) == "wide"
    assert tightness_label(0.9) == "medium"
    assert tightness_label(0.75) == "snug"
