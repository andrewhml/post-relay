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
- explicit draft media selection CLI for numbered contact-sheet keep/remove/lead/post-type edits
- dry-run Discord preview payload CLI with ordered included image paths and missing-file checks
- schedule and publish-approval CLI without live publishing
- sanitized read-only Meta Graph validation CLI
- controlled single-image and carousel Meta publish validation CLIs with dry-run planning, approval guards, optional staged-R2 URL resolution, container creation/status polling/publish execution, and sanitized attempt logging
- no-network R2 staging plan CLI for draft media and generated review artifacts
- guarded R2 staging upload/cleanup CLI with recorded-object-only deletion and explicit `--execute` safeguards
- explicit Instagram capability matrix separating publishable fields from local/review-only metadata
- guarded draft workflow state model
- no-network private DM intake harness for user-initiated post conversations and draft-context updates
- live-capable private Discord DM selection sender/poller for Discord-only selection smoke tests, guarded by environment-provided bot credentials

## Proven setup facts
- Meta app: Post Relay
- App ID: `936195858780647`
- Facebook Page ID: `998312870038313`
- Instagram Account ID: `17841400498120050`
- Working auth/read route: `graph.facebook.com`
- `graph.instagram.com` returned `Invalid platform app` in current setup

## Immediate goals
1. Define the Post Relay agent baseline as a specialized content curator and social media manager with focused skills for media curation, hook-first post packaging, factuality/sensitivity, scheduling, approvals, and Instagram capability checks
2. Add a private-DM-first, user-initiated Discord workflow where Andrew can start a post conversation at any time and provide context as needed
3. Let Andrew choose post type, select X photos from Y suggested draft photos, align on hook/caption/hashtags/location/schedule, and approve the complete package in DM before any live carousel post
4. After the user-initiated DM workflow is working effectively and proven, add agent-initiated suggestions from safe local opportunity triggers such as new media, cadence/inactivity, life/trip context, relevant events, or trend timing
5. Use staged public HTTPS media for publish validation while preserving dry-run, double-approval, and explicit `--execute` safeguards
6. Run a guarded carousel publish smoke test only after Discord DM selection/review is proven and a safe staged carousel draft is explicitly approved

## Agent handoff
Future agents should start with `AGENTS.md`, then `docs/plans/current-agent-roadmap.md`. The durable plan for local/NAS sources, review artifacts, and Cloudflare R2 staging is `docs/plans/content-pipeline-r2-staging-plan.md`. The specialized agent baseline is `docs/plans/postrelay-agent-operating-baseline.md`. The current private-DM conversation plan is `docs/plans/discord-dm-conversation-orchestration.md`, and the Discord-before-live-publish selection/review plan is `docs/plans/discord-photo-selection-before-carousel-smoke.md`.

## Local CLI
Use the project virtualenv when running locally:

```bash
.venv/bin/python -m pytest -q
.venv/bin/post-relay db init --db data/post_relay.sqlite
.venv/bin/post-relay index scan --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay library stats --db data/post_relay.sqlite
.venv/bin/post-relay meta validate-readonly --env-file .env --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --image-url "$POST_RELAY_TEST_IMAGE_URL" --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --image-url "$POST_RELAY_TEST_IMAGE_URL" --db data/post_relay.sqlite --env-file .env --execute
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --image-url "https://example.com/first.jpg" --image-url "https://example.com/second.jpg" --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-edit --draft-id 1 --lead 3 --keep 1,3,5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-plan --draft-id 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-accept --draft-id 1 --caption-index 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-plan --draft-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-preview --draft-id 1 --target-count 5 --artifact-path data/artifacts/draft-1/contact-sheet.jpg --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-apply --draft-id 1 --select 3,1,5,7,8 --lead 3 --target-count 5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay dm intake --message "start a post about Kyoto night market" --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay dm intake --message "make this cinematic and less touristy" --draft-id 1 --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-send --draft-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-poll --draft-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-apply --draft-id 1 --message "select 3,1,5,7,8 lead 3" --target-count 5 --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-plan --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute
.venv/bin/post-relay drafts r2-cleanup --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute --reason "publish complete"
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

Candidate groups currently use the indexed photo file's parent folder as the first reviewable travel set boundary. A folder with multiple photos is recommended as a carousel; a one-photo folder is recommended as a single image post. Draft records can be created from candidate groups and start in the `drafting` state with placeholder caption/location/hashtag fields. Draft preview packages print a stable local review format with ordered included photo paths, unresolved context notes, persisted context questions, and allowed next actions before Discord delivery is added. `drafts artifacts render` creates ordered thumbnails plus a contact sheet under the configured local artifact root and leaves source media unchanged. `drafts media-plan` prints the numbered draft media list for contact-sheet review; `drafts media-edit` applies explicit lead/cover, keep/remove, and post-type choices to the underlying candidate media, updates ordering/roles/inclusion, and invalidates active approvals as a material edit. Drafts can be submitted for review, approved for queueing, and edited locally; material edits after approval invalidate active approvals and move the draft back to `needs_edits`. Dry-run Discord preview payloads reuse the draft review text, list ordered existing included image attachment paths, and report missing image files without sending anything. Queue-approved drafts can be scheduled, moved into final publish-approval review, and explicitly approved for publishing; this only updates local state and approval records and does not call any live publishing API. The Meta Graph validation command loads tokens only from environment/private `.env`, redacts secrets, uses `graph.facebook.com` by default, and only calls read-only account visibility endpoints. Controlled single-image publish validation requires a `ready_to_publish` `single_image` draft, a public HTTPS image URL, and `--execute` before it calls Meta media container or publish endpoints; dry-run mode records a sanitized planned attempt without network calls. Controlled carousel publish validation requires a `ready_to_publish` `carousel` draft and one public HTTPS image URL per selected draft image; execution creates one child media container per image, creates a carousel container from those child ids, polls the carousel container, publishes only when ready, and stores sanitized attempt records. No live carousel smoke test has been run yet. `drafts r2-stage-plan` creates a no-network, no-credential dry-run plan for uploading the ordered draft media and already-generated local review artifacts to the configured temporary R2 staging bucket/domain; object keys are sanitized and do not expose local paths. `drafts r2-stage-upload` remains dry-run by default and only uploads/records planned objects when `--execute` is provided. `drafts r2-cleanup` also defaults to dry-run and, with `--execute`, deletes only SQLite-recorded uploaded objects whose keys remain under the configured Post Relay prefix. R2 remains temporary staging only; local/NAS source media remains the source of truth and is never mutated.

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
