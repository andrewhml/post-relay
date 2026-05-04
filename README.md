# Post Relay

Local-first Instagram content workflow for Andrew's `andrewhml` creator account.

## Current status
Early local-first MVP scaffold with:
- SQLite schema for sources, photos, candidate groups, drafts, and approvals
- local photo source config loading
- folder-based media indexing
- library statistics CLI
- candidate group builder/list CLI
- draft create/list/preview CLI
- local draft review artifact CLI for ordered thumbnails/contact sheets without source mutation
- draft context question generate/list CLI
- draft approval/edit CLI with approval invalidation on material edits
- dry-run Discord preview payload CLI with ordered image path and missing-file checks
- schedule and publish-approval CLI without live publishing
- sanitized read-only Meta Graph validation CLI
- controlled single-image and carousel Meta publish validation CLIs with dry-run planning, approval guards, container creation/status polling/publish execution, and sanitized attempt logging
- guarded draft workflow state model

## Proven setup facts
- Meta app: Post Relay
- App ID: `936195858780647`
- Facebook Page ID: `998312870038313`
- Instagram Account ID: `17841400498120050`
- Working auth/read route: `graph.facebook.com`
- `graph.instagram.com` returned `Invalid platform app` in current setup

## Immediate goals
1. Produce a safe no-network R2 staging plan for draft media and generated review artifacts
2. Upload publish-ready media to R2 only when needed, then clean up staged cloud copies after successful publish or explicit cleanup
3. Wire publish validation to use staged public HTTPS media while preserving dry-run, double-approval, and explicit `--execute` safeguards

## Agent handoff
Future agents should start with `AGENTS.md`, then `docs/plans/current-agent-roadmap.md`. The durable plan for local/NAS sources, review artifacts, and Cloudflare R2 staging is `docs/plans/content-pipeline-r2-staging-plan.md`.

## Local CLI
Use the project virtualenv when running locally:

```bash
.venv/bin/python -m pytest -q
.venv/bin/post-relay db init --db data/post_relay.sqlite
.venv/bin/post-relay index scan --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay library stats --db data/post_relay.sqlite
.venv/bin/post-relay meta validate-readonly --env-file .env --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --image-url "$POST_RELAY_TEST_IMAGE_URL" --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --image-url "$POST_RELAY_TEST_IMAGE_URL" --db data/post_relay.sqlite --env-file .env --execute
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --image-url "https://example.com/first.jpg" --image-url "https://example.com/second.jpg" --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts submit --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --draft-id 1 --approved-by andrew --notes "Content direction approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts edit --draft-id 1 --caption "Draft caption" --db data/post_relay.sqlite
.venv/bin/post-relay drafts schedule --draft-id 1 --scheduled-for "2026-05-05T09:30:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay drafts request-publish-approval --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve-publish --draft-id 1 --approved-by andrew --notes "Final approval" --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions generate --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions list --draft-id 1 --db data/post_relay.sqlite
```

Candidate groups currently use the indexed photo file's parent folder as the first reviewable travel set boundary. A folder with multiple photos is recommended as a carousel; a one-photo folder is recommended as a single image post. Draft records can be created from candidate groups and start in the `drafting` state with placeholder caption/location/hashtag fields. Draft preview packages print a stable local review format with ordered photo paths, unresolved context notes, persisted context questions, and allowed next actions before Discord delivery is added. `drafts artifacts render` creates ordered thumbnails plus a contact sheet under the configured local artifact root and leaves source media unchanged. Drafts can be submitted for review, approved for queueing, and edited locally; material edits after approval invalidate active approvals and move the draft back to `needs_edits`. Dry-run Discord preview payloads reuse the draft review text, list ordered existing image attachment paths, and report missing image files without sending anything. Queue-approved drafts can be scheduled, moved into final publish-approval review, and explicitly approved for publishing; this only updates local state and approval records and does not call any live publishing API. The Meta Graph validation command loads tokens only from environment/private `.env`, redacts secrets, uses `graph.facebook.com` by default, and only calls read-only account visibility endpoints. Controlled single-image publish validation requires a `ready_to_publish` `single_image` draft, a public HTTPS image URL, and `--execute` before it calls Meta media container or publish endpoints; dry-run mode records a sanitized planned attempt without network calls. Controlled carousel publish validation requires a `ready_to_publish` `carousel` draft and one public HTTPS image URL per selected draft image; execution creates one child media container per image, creates a carousel container from those child ids, polls the carousel container, then publishes only after it is `FINISHED`. Publish attempts persist sanitized image URLs, captions, remote container/media ids, carousel child container ids, status codes, and failure messages without storing access tokens.

Discord/image-preview development should use check-in tests before live messaging: start with a local directory of fixture photos, verify the dry-run payload includes the expected image paths/order, then smoke-test Discord delivery only after the local payload behavior is stable.

## Local secrets and machine config
Use a private `.env` file based on `.env.example`.
Do not paste tokens or secrets into chat.

Use a local machine config at `config/photo_sources.yaml`; it is gitignored because it contains machine-specific local/NAS paths. The current local config includes:
- NAS 2024 processed folder: `/Volumes/Media/photos/2024 Photos/Processed`
- Local Mac 2025 processed folder: `/Users/andrewlee/Pictures/2025 Photos/Processed`
- R2 staging bucket: `post-relay-publish`
- R2 S3 endpoint: `https://d79fef40225063d4b0e2d2cb33b346d0.r2.cloudflarestorage.com`
- R2 public custom domain: `https://peddocks.net`
