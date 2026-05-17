# Live carousel publish smoke preflight — 2026-05-17

This note captures safe preflight work for the guarded live Instagram carousel publish smoke milestone.

## Scope

Goal: prepare for one guarded live Instagram carousel publish smoke test through the official Meta Graph route, preferably using staged R2 public HTTPS URLs.

Safety boundary: no live Meta publish execution was run while preparing this note. The live command remains blocked until the draft is intentionally moved through both approval gates, selected media are staged to public HTTPS URLs, a dry run is reviewed, and Andrew explicitly authorizes `meta validate-carousel-publish --execute` in the active session.

## Local branch

- Current preflight refresh branch: `feat/live-carousel-publish-smoke-execution`
- Base: synced `main` after PR #47 was squash-merged.
- Earlier baseline branch: `feat/live-carousel-publish-smoke-notes`, started after PR #42.

## Candidate smoke draft

Current local candidate for the smoke test remains:

- Draft ID: `2`
- Candidate: `2025 Photos / Processed`
- Post type: `carousel`
- Current local status at refreshed preflight: `drafting`
- Caption present: yes
- Selected/included media count: 5
- Active draft approval: no
- Active publish approval: no
- Uploaded staged R2 media records: no
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
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-plan --draft-id 2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --image-url https://example.com/1.jpg --image-url https://example.com/2.jpg --image-url https://example.com/3.jpg --image-url https://example.com/4.jpg --image-url https://example.com/5.jpg --db data/post_relay.sqlite --dry-run
```

Observed safe preflight result:

- Full suite after PR #47 merge: `168 passed`.
- Meta read-only dry run resolved the Graph route as `https://graph.facebook.com`, used API version `v19.0`, redacted the token, and printed `No publishing endpoints will be called.`
- Local draft inventory shows draft `#2` as `carousel, drafting`; draft `#1` is the earlier posted single-image smoke record.
- Draft `2` still has a non-empty Mt. Cook caption, location, hashtags, alt text, and five included carousel media in the intended selected order.
- R2 staging plan is still available as a dry run and prints `No network calls were made.`
- Staged-R2 carousel publish dry run is blocked before publish planning because there are zero uploaded staged R2 media records for draft `2`.
- Manual-URL carousel publish dry run is blocked before publish planning because draft `2` is not yet `ready_to_publish`.
- No Discord DMs were sent.
- No R2 upload execution was run from this preflight refresh.
- No Meta publishing endpoints were called.

## Current blockers before live carousel execute

The draft does not yet satisfy the required live publish gates:

1. Draft status must be `ready_to_publish`; current status is `drafting`.
2. Active draft approval must exist; none exists for draft `2`.
3. Active publish approval must exist; none exists for draft `2`.
4. Staged R2 media upload execution must be run, or explicit public HTTPS image URLs must be supplied.
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

Only after Andrew explicitly approves the live smoke test in the active session:

```bash
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env --execute
```

## Post-execution documentation target

If live execution succeeds, update:

- `docs/publishing/carousel-smoke-test.md`
- `docs/plans/current-agent-roadmap.md`

Record only sanitized observed behavior: ordered child container ids, carousel container id, container status, published media id, local draft status transition, and any Meta account/API limitation. Do not record access tokens, app secrets, or private signed URL query values.
