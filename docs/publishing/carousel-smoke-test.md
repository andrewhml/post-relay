# Controlled carousel publish smoke test

This runbook is for validating carousel publishing through the official Meta Graph route after the local dry-run harness is green.

## Safety invariants

- Use only the official `graph.facebook.com` route.
- Do not paste tokens or app secrets into chat, commits, logs, or screenshots.
- Do not run the live command unless Andrew explicitly authorizes it in the active session.
- The post must already be `ready_to_publish`, which means it passed both content approval and publish approval.
- Start with `--dry-run`; only run `--execute` after the dry-run output is reviewed.
- Use a small, safe carousel media set that is okay to appear publicly on `andrewhml`.
- Before this live smoke test, Andrew should have selected the final carousel photos from a larger suggested set through the Discord selection flow documented in `docs/plans/discord-photo-selection-before-carousel-smoke.md`.

## Required local setup

A private `.env` file or shell environment must provide:

```bash
POST_RELAY_USER_ACCESS_TOKEN=<private token>
POST_RELAY_INSTAGRAM_ACCOUNT_ID=17841400498120050
POST_RELAY_META_GRAPH_BASE_URL=https://graph.facebook.com
POST_RELAY_META_GRAPH_VERSION=v19.0
```

Each carousel image URL must be publicly reachable by Meta over HTTPS. Local filesystem paths are not accepted by the Graph media container endpoint. Prefer the staged-R2 path when possible so publish validation resolves the currently selected draft media order from recorded uploaded `draft_media` objects.

## Required draft state

The draft must satisfy all of these:

- `post_type = carousel`
- at least two selected candidate images
- no more than ten selected candidate images
- one public HTTPS `--image-url` argument per selected candidate image, in draft image order, or uploaded staged-R2 `draft_media` records for every selected image
- non-empty caption stored on the draft record
- active draft approval exists
- active publish approval exists
- `status = ready_to_publish`

Useful local flow for preparing a carousel draft:

```bash
.venv/bin/post-relay drafts create --candidate-id <carousel-candidate-id> --db data/post_relay.sqlite
.venv/bin/post-relay drafts edit --post-id <post-id> --caption "Approved carousel caption" --db data/post_relay.sqlite
.venv/bin/post-relay drafts submit --post-id <post-id> --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --post-id <post-id> --approved-by andrew --notes "Carousel direction approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts schedule --post-id <post-id> --scheduled-for "2026-05-05T09:30:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve-publish --post-id <post-id> --approved-by andrew --notes "Final carousel approval" --db data/post_relay.sqlite
```

## Dry run

Preferred staged-R2 path:

```bash
.venv/bin/post-relay drafts r2-stage-upload \
  --post-id <post-id> \
  --config config/photo_sources.yaml \
  --db data/post_relay.sqlite

.venv/bin/post-relay drafts r2-stage-upload \
  --post-id <post-id> \
  --config config/photo_sources.yaml \
  --db data/post_relay.sqlite \
  --execute

.venv/bin/post-relay meta validate-carousel-publish \
  --post-id <post-id> \
  --from-staged-r2 \
  --config config/photo_sources.yaml \
  --db data/post_relay.sqlite \
  --dry-run
```

Manual public URL path:

```bash
.venv/bin/post-relay meta validate-carousel-publish \
  --post-id <post-id> \
  --image-url "https://example.com/first.jpg" \
  --image-url "https://example.com/second.jpg" \
  --db data/post_relay.sqlite \
  --dry-run
```

Review that:

- output starts with `Carousel publish validation`
- status is `planned`
- every image URL is sanitized if it contains secret-like query params
- staged-R2 mode reports the resolved image count and preserves the selected draft media order
- output says `No Meta publishing endpoints were called.`

## Live execution

Only after Andrew explicitly authorizes the live carousel smoke test:

Preferred staged-R2 path:

```bash
.venv/bin/post-relay meta validate-carousel-publish \
  --post-id <post-id> \
  --from-staged-r2 \
  --config config/photo_sources.yaml \
  --db data/post_relay.sqlite \
  --env-file .env \
  --execute
```

Manual public URL path:

```bash
.venv/bin/post-relay meta validate-carousel-publish \
  --post-id <post-id> \
  --image-url "https://example.com/first.jpg" \
  --image-url "https://example.com/second.jpg" \
  --db data/post_relay.sqlite \
  --env-file .env \
  --execute
```

Expected request sequence:

1. `POST /{ig-user-id}/media` with `image_url` and `is_carousel_item=true` for each child image.
2. `POST /{ig-user-id}/media` with `media_type=CAROUSEL`, comma-separated `children`, and the approved draft caption.
3. `GET /{carousel-creation-id}?fields=id,status_code`.
4. `POST /{ig-user-id}/media_publish` with the carousel creation id after the container is `FINISHED`.

Expected success indicators:

- `Status: published`
- one child container id per image
- `Carousel container ID: <meta carousel container id>`
- `Carousel container status: FINISHED`
- `Published media ID: <meta media id>`
- draft status moves to `posted`

## Verification after execution

```bash
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup \
  --post-id <post-id> \
  --config config/photo_sources.yaml \
  --db data/post_relay.sqlite
.venv/bin/python -m pytest -q
```

Record the observed Meta behavior, sanitized ids/statuses, and any account/app limitation in `docs/plans/current-agent-roadmap.md`. If staged R2 was used and the live publish succeeded, review the cleanup dry-run output and only then run `drafts r2-cleanup --execute --reason "publish complete"` to delete recorded Post Relay-created staging objects.

## Current preflight notes

- `docs/publishing/live-carousel-smoke-preflight-2026-05-17.md` records the current safe preflight after PR #47. It identifies draft `2` as the current local carousel candidate, confirms selected media and R2 dry-run planning, and documents the remaining approval, staged-media, dry-run, and active-session live-authorization blockers. No R2 upload execution or Meta publishing endpoints were called.

## Current implementation status

Implemented locally with tests only. No live carousel publish smoke test has been run yet.

Local validation covers:

- ready-to-publish carousel draft guard
- one public HTTPS URL per selected draft image
- sanitized dry-run attempt recording without network calls
- child media container creation with `is_carousel_item=true`
- carousel container creation with `media_type=CAROUSEL` and ordered child ids
- carousel status polling before publish
- publish only after `FINISHED`
- sanitized audit records for image URLs, child container ids, carousel container id, status, and published media id
- staged-R2 URL resolution via `--from-staged-r2`, preserving selected draft media order and ignoring staged artifacts
