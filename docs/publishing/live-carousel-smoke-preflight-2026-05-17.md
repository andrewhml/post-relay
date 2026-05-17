# Live carousel publish smoke preflight — 2026-05-17

This note captures the safe preflight work for milestone `feat/live-carousel-publish-smoke-notes`.

## Scope

Goal: prepare for one guarded live Instagram carousel publish smoke test through the official Meta Graph route, preferably using staged R2 public HTTPS URLs.

Safety boundary: no live Meta publish execution was run while preparing this note. The live command remains blocked until Andrew explicitly authorizes `meta validate-carousel-publish --execute` in the active session.

## Local branch

- Branch: `feat/live-carousel-publish-smoke-notes`
- Base: synced `main` after PR #42 was squash-merged.

## Candidate smoke draft

Current local candidate for the smoke test:

- Draft ID: `2`
- Candidate: `2025 Photos / Processed`
- Post type: `carousel`
- Current local status at preflight: `drafting`
- Caption present: yes
- Selected/included media count: 5
- Selected media order:
  1. `/Users/andrewlee/Pictures/2025 Photos/Processed/A7407045.jpg`
  2. `/Users/andrewlee/Pictures/2025 Photos/Processed/A7406964.jpg`
  3. `/Users/andrewlee/Pictures/2025 Photos/Processed/A7407027.jpg`
  4. `/Users/andrewlee/Pictures/2025 Photos/Processed/A7406996.jpg`
  5. `/Users/andrewlee/Pictures/2025 Photos/Processed/A7407032-2.jpg`

## Safe preflight commands run

```bash
.venv/bin/python -m pytest -q
.venv/bin/post-relay meta validate-readonly --env-file .env --dry-run
.venv/bin/post-relay drafts preview --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-plan --draft-id 2 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

Observed safe preflight result:

- Full suite before starting branch: `161 passed`.
- Meta read-only dry run resolved the Graph route as `https://graph.facebook.com` and did not call publishing endpoints.
- R2 staging plan for the 5 selected draft media was ready to upload and generated ordered public URLs under `https://peddocks.net/post-relay/staging/drafts/2/media/`.
- No Discord DMs were sent.
- No Meta publishing endpoints were called.
- No R2 upload execution was run from this preflight note.

## Current blockers before live carousel execute

The draft does not yet satisfy the required live publish gates:

1. Draft status must be `ready_to_publish`; current status is `drafting`.
2. Active draft approval must exist.
3. Active publish approval must exist.
4. Staged R2 upload execution must be run, or explicit public HTTPS image URLs must be supplied.
5. A staged-R2 or manual-URL carousel publish dry run must pass immediately before live execution.
6. Andrew must explicitly authorize the live Meta publish command in the active session.

## Expected next command sequence, after approval gates are intentionally completed

```bash
.venv/bin/post-relay drafts submit --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --draft-id 2 --approved-by andrew --notes "Carousel direction approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts schedule --draft-id 2 --scheduled-for "<approved-iso-timestamp>" --db data/post_relay.sqlite
.venv/bin/post-relay drafts request-publish-approval --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve-publish --draft-id 2 --approved-by andrew --notes "Final carousel smoke approval" --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --draft-id 2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --draft-id 2 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
```

Only after Andrew explicitly approves the live smoke test:

```bash
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env --execute
```

## Post-execution documentation target

If live execution succeeds, update:

- `docs/publishing/carousel-smoke-test.md`
- `docs/plans/current-agent-roadmap.md`

Record only sanitized observed behavior: ordered child container ids, carousel container id, container status, published media id, local draft status transition, and any Meta account/API limitation. Do not record access tokens, app secrets, or private signed URL query values.
