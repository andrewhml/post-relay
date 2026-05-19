# Contact Sheet Chat Design Refresh Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Use one rollback-safe branch and PR for this milestone.

**Goal:** Integrate the new `assets/contact sheet/` visual designs into Post Relay's local review artifacts and chat/Discord preview surfaces so Andrew sees clearer numbered contact sheets and final post previews in chat.

**Architecture:** Post Relay is currently a Python CLI/SQLite workflow, not a React app. Treat the provided React/CSS files as the authoritative visual/data contract, then port the deterministic pieces into local Python/Pillow renderers that produce static chat-safe image artifacts. Keep local source media immutable; render generated review/final-preview images under configured artifact/export roots; expose them through existing dry-run and live-capable Discord DM payload seams before any live-send changes.

**Tech Stack:** Python 3.9+, SQLite, Typer, Pillow, pytest. Reference design files: `assets/contact sheet/README.md`, `assets/contact sheet/INTEGRATION_PROMPT.md`, `assets/contact sheet/contact-sheet.jsx`, `assets/contact sheet/carousel-preview.jsx`, `assets/contact sheet/crop-helpers.js`, and `assets/contact sheet/contact-sheet-final.css`.

---

## Source design contract

Preserve these decisions from `assets/contact sheet/INTEGRATION_PROMPT.md`:

- Warm-dark theme: background `#14120f`, mat `#0c0b09`.
- Single amber accent `#e8a838`; do not introduce red/green selection accents.
- Number callouts are prominent amber chips with dark text.
- Filenames and crop metadata live below the image, not overlaid on it.
- Contact sheets use numbered photos plus a 5x5 chess-grid crop vocabulary (`A1` through `E5`).
- Lead/cover photo is marked with an amber outline and `LEAD` pill.
- Final carousel/post preview shows selected photos in confirmed order at one locked Instagram aspect ratio, with the first slide marked as lead and pagination dots.
- Crop helper behavior must match the JS source: `fitCrop`, `cropBox`, `chessFromAnchor`, `chessSpan`, `ratioLabel`, and `tightnessLabel`.

## Product scope for this milestone

In scope:

1. Port the crop/data contract to tested Python helpers.
2. Replace the current simple white contact sheet with a warm-dark numbered contact sheet image for local artifacts.
3. Add a final post preview artifact for selected/included media, using the same design language as `<CarouselPreview>`.
4. Wire dry-run/chat payload text to reference the new artifacts so a Discord DM can display them as attachments or fallback local paths.
5. Keep all behavior local-first and no-network by default.

Out of scope unless Andrew explicitly expands this milestone:

- React/Vite/Next web UI integration.
- Persistent manual crop-edit state in SQLite.
- Natural-language crop-edit parsing such as `shift 03 to B2`.
- Full-size lightbox/zoom behavior.
- Live Discord send behavior changes before the no-network payloads and artifact renderers are green.
- Any R2 upload execution or Meta publish execution.

## Current code seams

Existing contact-sheet rendering:

- `src/post_relay/review_artifacts.py`
  - `render_review_artifacts_for_draft(...)` creates ordered thumbnails and calls `_save_contact_sheet(...)`.
  - `_save_contact_sheet(...)` currently renders a simple white grid with a text header.
  - Large drafts are protected by `BoundedReviewArtifactPlan`; preserve that guard.

Existing final/post preview surfaces:

- `src/post_relay/final_publish_preview.py`
  - `FinalPublishPreview.to_text()` renders exact Meta-bound caption and selected staged media URLs.
  - No image artifact is currently generated here.
- `src/post_relay/publish_exports.py`
  - `drafts publish-exports render` creates publish-ready images and a simple publish contact sheet from exported images.
  - This is a good source for final-preview media when exports exist.

Existing chat/dry-run surfaces:

- `src/post_relay/discord_preview.py`
  - `DiscordSelectionPayload` can include `artifact_paths` and already mentions contact sheet fallbacks.
- `src/post_relay/discord_selection.py`
  - Selection text defines numbered review media and command fallback semantics.
- `src/post_relay/dm_operating_loop.py` and `src/post_relay/discord_dm.py`
  - DM next-action and live-capable send/poll flows should eventually point to/render these artifacts, but this milestone should prove dry-run behavior first.

## Data mapping

Map the design's `Photo` shape into Python as follows:

| Design field | Python source |
|---|---|
| `n` | `DraftMediaPlanItem.review_number` |
| `file` | `Path(local_file_path).name` |
| `src` | local file path for Pillow rendering; public URL only for future web/React surfaces |
| `w`, `h` | dimensions from `PIL.ImageOps.exif_transpose(image)` |
| `ratio` | default crop ratio for review; start with `1.0` for neutral contact-sheet crop references unless a selected final ratio is provided |
| `ax`, `ay` | default `0.5, 0.5` until crop adjustments are persisted |
| `tight` | default `1.0` until crop adjustments are persisted |
| lead | item role `primary` or first included media after selection |

For the final post preview, use the selected/included media order. Prefer exported publish assets when a matching publish-export package exists; otherwise render from source media as a local preview and label it as a preview, not a publish asset.

## Task 1: Port crop helpers from JS to Python

**Objective:** Create a tested, dependency-light Python equivalent of `assets/contact sheet/crop-helpers.js`.

**Files:**
- Create: `src/post_relay/contact_sheet_design.py`
- Create/modify: `tests/test_contact_sheet_design.py`

**Step 1: Write failing tests**

Test cases:

- `fit_crop(4032, 3024, 1, 0.5, 0.5)` returns the centered square crop box.
- `crop_box(photo, override_ratio=0.8)` applies `tight` scaling and override ratio.
- `chess_from_anchor(0.5, 0.5) == "C3"`.
- `chess_from_anchor(0.0, 0.0) == "A1"` and `chess_from_anchor(1.0, 1.0) == "E5"`.
- `chess_span(...)` matches the JS floor/ceil behavior.
- `ratio_label(0.8) == "4:5"`; `tightness_label(1.0) == "wide"`.

Run:

```bash
.venv/bin/python -m pytest tests/test_contact_sheet_design.py -q
```

Expected RED: import/module missing.

**Step 2: Implement minimal helper module**

Implement dataclasses/functions only; no artifact rendering in this task.

**Step 3: Verify**

```bash
.venv/bin/python -m pytest tests/test_contact_sheet_design.py -q
```

Expected GREEN.

## Task 2: Render warm-dark contact sheet artifacts

**Objective:** Replace the current simple contact sheet image with the warm-dark design language while preserving current artifact paths and source immutability.

**Files:**
- Modify: `src/post_relay/review_artifacts.py`
- Possibly create: `src/post_relay/chat_artifacts.py` if separating renderer code keeps `review_artifacts.py` small
- Modify: `tests/test_review_artifacts.py`
- Modify: `tests/test_cli.py` only if CLI output changes

**Step 1: Write failing tests**

Add tests that render two or three fixture images and assert:

- `contact-sheet-select.png` and `contact-sheet-crop.png` exist under `review_artifacts.root / draft-N`.
- Source image bytes are unchanged.
- The new sheet has a dark background pixel near the header/body, not white.
- The sheet includes expected dimensions for a three-column chat-safe layout or configured column count.
- Lead/number chip rendering is visible via an amber pixel sample or by exposing structured render metadata.
- `ReviewArtifactsPackage.to_text()` remains stable enough for CLI users and still lists the contact sheet path.

Run focused tests:

```bash
.venv/bin/python -m pytest tests/test_review_artifacts.py -q
```

Expected RED: current renderer is white/simple and lacks design rendering.

**Step 2: Implement renderer**

Port the visual hierarchy from `contact-sheet-final.css` into Pillow:

- Canvas: warm-dark `#14120f`.
- Header: `CONTACT SHEET`, photo count, `A1-E5 GRID`, title, optional subtitle.
- Body: 3-column grid by default, respecting `ReviewArtifactsConfig.contact_sheet_columns`.
- Each card:
  - square dark mat cell,
  - image letterboxed into the cell,
  - crop rectangle and 5x5 chess-grid overlay using ported crop helpers,
  - amber number sticker top-left,
  - optional lead pill/outline,
  - filename/ratio/anchor/tightness meta strip below.
- Footer: crop-talk examples from the design (`shift 03 to B2`, `tighten 06`, `lead 03`).

Use available system fonts if IBM Plex is unavailable; do not add a runtime network font dependency.

**Step 3: Verify**

```bash
.venv/bin/python -m pytest tests/test_review_artifacts.py tests/test_cli.py::test_cli_draft_artifacts_render_creates_local_review_artifacts -q
```

Then keep the existing bounded-large-set tests green.

## Task 3: Add final post preview artifact renderer

**Objective:** Create a local image artifact equivalent to `<CarouselPreview>` for the finalized post/chat confirmation step.

**Files:**
- Create/modify: `src/post_relay/final_post_artifacts.py` or `src/post_relay/chat_artifacts.py`
- Modify: `src/post_relay/cli.py`
- Create/modify: `tests/test_final_post_artifacts.py`
- Modify: `tests/test_final_publish_preview.py` if final preview text references the artifact

**Step 1: Write failing tests**

Fixture: a carousel draft with two or more selected/included images, caption text, and optional publish exports.

Assert:

- Renderer outputs high-DPI `final-post-preview.png` under a generated artifact root, e.g. `data/review_artifacts/draft-N/final-post-preview.png` or a new configured chat artifact root.
- Slides are rendered in included media order.
- The first slide/lead has an amber lead marker.
- All slides use one locked ratio, defaulting to 4:5 for carousel/feed preview unless explicitly overridden.
- Caption appears below the slides in the rendered artifact metadata/text object.
- No Discord, R2, or Meta calls are made.

Run:

```bash
.venv/bin/python -m pytest tests/test_final_post_artifacts.py -q
```

Expected RED: module/command missing.

**Step 2: Implement minimal renderer and CLI harness**

Suggested CLI:

```bash
.venv/bin/post-relay drafts final-preview-artifact render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

Keep output local-only:

```text
Final Post Preview Artifact
Post ID: 1
Preview image:
  data/review_artifacts/draft-1/final-post-preview.png
No Discord, R2, or Meta network calls were made.
```

If adding a new CLI namespace feels too broad, integrate this as an option on an existing command:

```bash
.venv/bin/post-relay meta final-publish-preview --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --render-artifact
```

Prefer the separate `drafts final-preview-artifact render` command if it keeps final visual preview independent from staged-R2/Meta-bound URL requirements.

**Step 3: Verify**

```bash
.venv/bin/python -m pytest tests/test_final_post_artifacts.py tests/test_cli.py -q
```

## Task 4: Wire dry-run Discord/chat payloads to the new artifacts

**Objective:** Make chat/display surfaces reference the improved artifacts without changing live send behavior first.

**Files:**
- Modify: `src/post_relay/discord_preview.py`
- Modify: `src/post_relay/dm_operating_loop.py` if next-action copy should recommend rendering/sending these artifacts
- Modify: `tests/test_discord_selection_payload.py`
- Modify: `tests/test_dm_operating_loop.py`

**Step 1: Write failing tests**

Assert that:

- `drafts discord-selection-preview --artifact-path ...` still reports local artifact references, and docs/copy now call the path a designed contact sheet artifact.
- The final publish/preflight next action recommends rendering/reviewing the final post preview artifact before approval/execution.
- Missing artifact paths still make `ready_to_send` false and are reported explicitly.
- Output remains source-path-safe in DM-facing copy where required.

Run:

```bash
.venv/bin/python -m pytest tests/test_discord_selection_payload.py tests/test_dm_operating_loop.py -q
```

Expected RED: current copy does not mention the new designed artifacts/final preview artifact.

**Step 2: Implement minimal copy/payload wiring**

Do not send Discord messages or upload artifacts in this task. Keep the live-capable commands' network behavior unchanged until the dry-run shape is proven.

**Step 3: Verify**

```bash
.venv/bin/python -m pytest tests/test_discord_selection_payload.py tests/test_dm_operating_loop.py -q
```

## Task 5: Update docs/handoff and run full verification

**Objective:** Make future agents aware of the new design contract, commands, and safety boundaries.

**Files:**
- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `docs/plans/current-agent-roadmap.md`
- Keep reference assets in: `assets/contact sheet/`

**Required docs updates:**

- Add the design refresh milestone to the roadmap as `feat/chat-design-refresh`.
- Mention the new artifact command(s) in README/AGENTS command lists.
- Document that the provided React files are design references for now; Post Relay renders static Pillow artifacts for CLI/Discord chat.
- Preserve the local-first/no-network/no-source-mutation constraints.

**Verification:**

Focused:

```bash
.venv/bin/python -m pytest tests/test_contact_sheet_design.py tests/test_review_artifacts.py tests/test_final_post_artifacts.py tests/test_discord_selection_payload.py tests/test_dm_operating_loop.py -q
```

Full suite:

```bash
.venv/bin/python -m pytest -q
```

Smoke commands after implementation:

```bash
.venv/bin/post-relay drafts artifacts render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-preview --draft-id 1 --target-count 5 --artifact-path data/review_artifacts/draft-1/contact-sheet-select.png --db data/post_relay.sqlite
.venv/bin/post-relay drafts final-preview-artifact render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

## Acceptance checklist

- [ ] Crop helper tests prove parity with the provided JS contract.
- [ ] Contact sheet artifacts use the warm-dark/amber design; Stage 1 is selection-only with no crop framing/grid/lead state, while Stage 2 uses the numbered/chess-grid crop vocabulary.
- [ ] Contact sheet filenames/metadata are below images, not overlaid.
- [ ] Final post preview artifact shows selected media in confirmed order with one locked ratio and lead marker.
- [ ] Existing large-set guardrails still block oversized full contact sheets.
- [ ] Existing source media immutability tests remain green.
- [ ] Dry-run Discord/chat payloads can reference the new artifacts before live sends change.
- [ ] No Discord, R2, or Meta network calls are introduced by rendering or dry-run preview commands.
- [ ] README, AGENTS, and roadmap tell future agents where the design files live and how to verify the milestone.
