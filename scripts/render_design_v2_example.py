from pathlib import Path

from PIL import Image, ImageDraw

from post_relay.candidates import build_candidate_groups
from post_relay.config import PhotoSource, PostRelayConfig, ReviewArtifactsConfig
from post_relay.contact_sheet_design import ContactSheetPhoto
from post_relay.db import connect_db, initialize_db
from post_relay.drafts import create_draft_from_candidate
from post_relay.final_post_artifacts import render_final_post_preview_artifact
from post_relay.indexer import index_photo_sources
from post_relay.media_selection import apply_draft_crop_feedback, apply_draft_media_selection
from post_relay.repository import list_candidate_groups, update_draft_content
from post_relay.review_artifacts import _save_contact_sheet

root = Path("/Users/andrewlee/workspace/personal/post-relay/data/review_artifacts/design-v2-example")
media = root / "processed" / "2026" / "granary-coffee"
media.mkdir(parents=True, exist_ok=True)
colors = [
    (210, 120, 80),
    (80, 130, 190),
    (180, 60, 70),
    (90, 90, 80),
    (30, 90, 130),
    (220, 220, 210),
    (190, 180, 160),
    (120, 100, 80),
    (70, 110, 70),
]
sizes = [
    (1200, 800),
    (800, 1200),
    (1000, 1000),
    (900, 1400),
    (1400, 900),
    (1600, 900),
    (900, 1350),
    (1200, 900),
    (900, 1200),
]
photos = []
for i, (size, color) in enumerate(zip(sizes, colors), start=1):
    im = Image.new("RGB", size, color)
    d = ImageDraw.Draw(im)
    for y in range(size[1]):
        shade = int(50 * y / size[1])
        d.line((0, y, size[0], y), fill=tuple(min(255, c + shade) for c in color))
    d.rectangle(
        (size[0] // 5, size[1] // 5, size[0] * 4 // 5, size[1] * 4 // 5),
        outline=(245, 235, 210),
        width=max(4, size[0] // 150),
    )
    d.text((size[0] // 2 - 30, size[1] // 2 - 20), chr(64 + i), fill=(20, 18, 15))
    path = media / f"IMG_48{20 + i}.jpg"
    im.save(path, quality=92)
    ratio = [1.0, 0.8, 1.0, 0.8, 1.0, 1.91, 0.8, 1.0, 1.0][i - 1]
    ax = [0.25, 0.5, 0.75, 0.25, 0.5, 0.75, 0.5, 0.75, 1.0][i - 1]
    ay = [0.25, 0.0, 0.5, 0.5, 0.5, 1.0, 1.0, 0.75, 0.0][i - 1]
    tight = [1, 1, 0.88, 1, 1, 1, 0.88, 0.88, 0.82][i - 1]
    photos.append(
        (
            ContactSheetPhoto(i, path.name, path.as_posix(), size[0], size[1], ratio, ax, ay, tight),
            im.copy(),
            i == 5,
        )
    )

_save_contact_sheet(
    photos,
    root / "contact-sheet-select.png",
    title="Granary Coffee · feed candidates",
    mode="select",
    max_px=223,
    columns=3,
)
_save_contact_sheet(
    [photos[i - 1] for i in [5, 3, 2, 7]],
    root / "contact-sheet-crop.png",
    title="Granary Coffee · feed candidates",
    mode="crop",
    max_px=223,
    columns=3,
)

example_db = root / "example.sqlite"
if example_db.exists():
    example_db.unlink()
connection = connect_db(example_db)
initialize_db(connection)
index_photo_sources(
    connection,
    PostRelayConfig(photo_sources=[PhotoSource(name="example", root=root / "processed", source_type="processed_folder")]),
)
build_candidate_groups(connection)
candidate = list_candidate_groups(connection)[0]
draft = create_draft_from_candidate(connection, candidate.id)
update_draft_content(
    connection,
    draft.id,
    caption="Saturday mornings at the Granary. New seasonal blend now pouring — say hi to our baristas. ☕",
    hashtags=[],
    location_text="Granary Coffee, San Francisco",
)
apply_draft_media_selection(connection, draft.id, lead=5, keep=[5, 3, 2, 7], post_type="carousel")
apply_draft_crop_feedback(
    connection,
    draft.id,
    crop_edits={5: {"anchor": "C3", "ratio": "4:5"}, 3: {"anchor": "E3", "ratio": "4:5"}, 2: {"anchor": "C1", "ratio": "4:5"}, 7: {"anchor": "B5", "ratio": "4:5"}},
)
render_final_post_preview_artifact(
    connection,
    draft.id,
    ReviewArtifactsConfig(root=root, thumbnail_max_px=223, contact_sheet_columns=3),
)
connection.close()
html = """<!doctype html>
<html>
<head>
  <meta charset='utf-8'>
  <title>Post Relay three-stage review example</title>
  <style>
    body { margin:0; background:#0c0b09; color:#ece8de; font-family:-apple-system,BlinkMacSystemFont,sans-serif; padding:32px; }
    .wrap { max-width:760px; margin:auto; }
    img { width:720px; max-width:100%; display:block; margin:16px 0 36px; border-radius:8px; box-shadow:0 20px 60px rgba(0,0,0,.35); }
    h1 { font-size:20px; margin-top:0; }
    p { color:#b8b3a7; line-height:1.45; }
    code { color:#e8a838; }
  </style>
</head>
<body>
  <div class='wrap'>
    <h1>Post Relay three-stage review</h1>
    <p>Generated from the updated design package as high-DPI PNG assets: Stage 1 Select, Stage 2 Crop, Stage 3 Preview. Organization and feedback can happen at any stage.</p>
    <h2>Stage 1 · Select</h2>
    <p>Full library view with letter stickers only. No crop frame, grid, or lead marker is shown here; this stage is just for choosing the images.</p>
    <img src='contact-sheet-select.png' alt='Stage 1 select contact sheet example'>
    <h2>Stage 2 · Crop</h2>
    <p>Selected subset only, in carousel order, with crop overlays, A1–E5 grid, and lead marker.</p>
    <img src='contact-sheet-crop.png' alt='Stage 2 crop contact sheet example'>
    <h2>Stage 3 · Preview</h2>
    <p>Final approval preview at locked 4:5 ratio, with ordered slides, pagination chips, caption, and metadata tags.</p>
    <img src='draft-1/final-post-preview.png' alt='Final post approval preview example'>
  </div>
</body>
</html>
"""
(root / "index.html").write_text(html)
for _, image, _ in photos:
    image.close()
print(root / "index.html")
