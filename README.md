# Post Relay

Local-first Instagram content workflow for Andrew's `andrewhml` creator account.

## Current status
Early local-first MVP scaffold with:
- SQLite schema for sources, photos, candidate groups, drafts, and approvals
- local photo source config loading
- folder-based media indexing with local image metadata enrichment for dimensions, orientation/aspect ratio, and available EXIF date/camera/lens fields
- library statistics CLI
- candidate group builder/list CLI
- post create/list/preview CLI (currently under the existing `drafts` command namespace)
- local post review artifact CLI for staged ordered thumbnails/contact sheets without source mutation: Stage 1 selection by default, Stage 2 crop after confirmed media selection except for single-media posts, Stage 3 final preview only after accepted copy/metadata
- post context question generate/list CLI
- post content approval/edit CLI with approval invalidation on material edits
- explicit post media selection CLI for numbered contact-sheet keep/remove/lead/post-type edits
- local crop/center feedback CLI using the designed A1-E5 grid vocabulary (`shift 03 to B2`, `center 05`, `tighten 06`) with approval invalidation on material crop edits
- warm-dark Pillow-rendered contact sheets and final post preview artifacts based on `assets/contact sheet/` React/CSS design references
- dry-run Discord preview payload CLI with ordered included image paths and missing-file checks
- schedule and publish-approval CLI without live publishing
- sanitized read-only Meta Graph validation CLI
- controlled single-image and carousel Meta publish validation CLIs with dry-run planning, approval guards, staged-R2 URL resolution, schedule enforcement, container creation/status polling/publish execution, hashtags merged into the Meta caption payload, and sanitized attempt logging
- no-network scheduled publish preflight/execute wrapper for due staged-R2 posts that re-validates schedule, durable active approvals, and media completeness before Meta execution
- scriptless unattended publish planning that verifies a ready approved staged-R2 post before its due time and emits the exact guarded scheduled job command/prompt, avoiding per-post helper scripts
- no-network final publish preview that shows the exact Meta-bound caption, selected staged media URLs, publishable fields, and local/review-only metadata before live execution
- Instagram-optimized local publish exports for 4:5 portrait feed/carousel assets, including mixed-orientation warnings and contact sheets built from the actual exported files
- resolved Meta location tags stored separately from freeform location text, with draft-aware candidate search/clarification, explicit `location_id` final preview/publish payloads only after reviewed Page selection and reapproval
- local post-publish analytics snapshots that capture published media ids, final Meta-bound caption/media URLs, schedule vs actual publish time, resolved location tag, and export dimensions from staged media records without network calls
- guarded read-only insights fetch/storage for published media behind explicit `analytics insights-fetch --execute`, with dry-run default and local metric audit records
- local recommendation feedback summaries from stored post-publish snapshots and read-only insight metrics, with advisory-only output and no network/state mutation
- local follower-growth summaries from stored read-only account metric snapshots, plus guarded dry-run/default `analytics follower-fetch` for account-level follower/media counts
- guarded Meta user-token extension helper (`meta token-extend`) that dry-runs by default, exchanges valid short-lived tokens only with `--execute`, and updates `.env` only with `--update-env`
- guarded R2 staging upload/cleanup CLI with recorded-object-only deletion and explicit `--execute` safeguards
- explicit Instagram capability matrix separating publishable fields from local/review-only metadata
- guarded post lifecycle state model where `drafting` is a status
- no-network private DM intake harness for user-initiated post conversations and post-context updates
- live-capable private Discord DM selection sender/poller for Discord-only selection smoke tests, guarded by environment-provided bot credentials
- live-capable private Discord DM guided review sender/poller plus no-network apply fallback for accepting hook/caption/metadata decisions from DM-style replies
- live-capable private Discord DM scheduling guidance sender/poller plus double-confirmed final-publish-approval sender/poller and no-network apply fallbacks
- no-network `dm next-action` planner that chooses the next private-DM operating-loop step from the active thread/post status, shows all locally scheduled posts before recommending another slot, treats stored final publish approval as durable until a material edit invalidates it, leads drafting/needs-edits posts through the Stage 1/2/3 local artifact loop, and keeps ready-to-publish guidance no-`--execute` by default without sending Discord, R2, or Meta requests
- local post opportunity model and safe trigger checks for agent-initiated suggestions with dry-run planning, dedupe, snooze/dismiss respect, manual seeds, proactive DM planning/mark-sent controls, and candidate-to-draft conversion, without sending DMs
- private DM intake narrowing guardrails that ask for more specific cues before suggesting huge weak candidate matches and warn before rendering contact sheets for large matched sets
- local semantic DM candidate matching using folder/year/filename descriptors, simple aliases, and source-path-safe match rationale
- bounded review artifact planning that blocks oversized full contact-sheet renders and returns a DM-safe first-pass narrowing plan without source paths or network calls

## Proven setup facts
- Meta app: Post Relay
- App ID: `936195858780647`
- Facebook Page ID: `998312870038313`
- Instagram Account ID: `17841400498120050`
- Working auth/read route: `graph.facebook.com`
- `graph.instagram.com` returned `Invalid platform app` in current setup

## Immediate goals
1. Use recommendation feedback summaries and follower-growth snapshots as local advisory baselines for the next reviewed travel post; keep improving deterministic suggestions as more real posts collect data
2. Practice the private-DM-first operating loop with the refreshed warm-dark review/final-preview artifacts while keeping live Discord sends behind explicit operator authorization
3. Keep improving the private-DM workflow for selecting photos, accepting hook-first captions/metadata, scheduling, and recording local approvals; `dm next-action` should lead with local Stage 1/2/3 artifacts and no-network preflights before any live-capable Discord or Meta command
4. Keep agent-initiated suggestions controlled through `opportunities dm-plan`, `opportunities mark-dm-sent`, snooze/dismiss, and candidate conversion; no proactive Discord send should happen unless explicitly authorized in the active session
5. Keep local media discovery enrichment no-network and auditable: `index scan` extracts image dimensions plus available EXIF date/camera/lens metadata from local files only; use this as the next baseline before adding generated tags, embeddings, or Immich/NAS enrichment.

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
.venv/bin/post-relay meta token-extend --env-file .env
# Execute only after pasting a fresh short-lived token into .env; add --update-env to replace it with the returned long-lived token:
.venv/bin/post-relay meta token-extend --env-file .env --execute --update-env
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --image-url "$POST_RELAY_TEST_IMAGE_URL" --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --image-url "$POST_RELAY_TEST_IMAGE_URL" --db data/post_relay.sqlite --env-file .env --execute
# Early live publish override, only with explicit active-session authorization:
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env --execute --publish-now
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --image-url "https://example.com/first.jpg" --image-url "https://example.com/second.jpg" --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-carousel-publish --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta final-publish-preview --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay meta publish-scheduled --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay meta unattended-publish-plan --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env
# Execute only when due and explicitly authorized in the active session:
.venv/bin/post-relay meta publish-scheduled --draft-id 2 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env --execute
.venv/bin/post-relay analytics snapshot --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay analytics insights-plan --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay analytics insights-fetch --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay analytics feedback-summary --draft-id 2 --db data/post_relay.sqlite
.venv/bin/post-relay analytics feedback-summary --limit 10 --db data/post_relay.sqlite
.venv/bin/post-relay analytics follower-fetch --instagram-account-id 17841400498120050 --db data/post_relay.sqlite
.venv/bin/post-relay analytics follower-summary --target-followers 5000 --db data/post_relay.sqlite
# Execute only for read-only insights collection when the token has instagram_manage_insights:
.venv/bin/post-relay analytics insights-fetch --draft-id 2 --metric reach --metric likes --metric comments --metric saved --metric shares --db data/post_relay.sqlite --env-file .env --execute
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --draft-id 1 --stage select --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-edit --draft-id 1 --lead 3 --keep 1,3,5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --draft-id 1 --stage crop --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts crop-feedback --draft-id 1 --shift 3:B2 --center 5 --tighten 6 --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-plan --draft-id 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-accept --draft-id 1 --caption-index 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts final-preview-artifact render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts publish-exports render --draft-id 1 --profile feed_portrait_3x4 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts location-candidates --draft-id 1 --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay drafts location-candidates --draft-id 1 --query "Gwangjang Market Seoul" --env-file .env --db data/post_relay.sqlite
.venv/bin/post-relay drafts location-tag-set --draft-id 1 --page-id <facebook-page-location-id> --name "Seoul, Korea" --source pages/search --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-plan --draft-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-preview --draft-id 1 --target-count 5 --artifact-path data/review_artifacts/draft-1/contact-sheet-select.png --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-apply --draft-id 1 --select 3,1,5,7,8 --lead 3 --target-count 5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay dm intake --message "start a post about Kyoto night market" --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay dm next-action --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay dm next-action --draft-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay dm intake --message "make this cinematic and less touristy" --draft-id 1 --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-intake-poll --after-message-id <last-known-dm-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-send --draft-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-poll --draft-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-apply --draft-id 1 --message "select 3,1,5,7,8 lead 3" --target-count 5 --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-guided-review-send --draft-id 1 --mood cinematic --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-guided-review-poll --draft-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-guided-review-apply --draft-id 1 --message "location: Seoul, South Korea; story: night market alleys; mood: cinematic; hook: food and light; caption 1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-schedule-send --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-schedule-poll --draft-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-schedule-apply --draft-id 1 --message "slot 1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-send --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-poll --draft-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-poll --draft-id 1 --channel-id <discord-dm-channel-id> --after-message-id <confirmation-prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-apply --draft-id 1 --message "approve publish" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-apply --draft-id 1 --message "confirm publish approval for post #1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --execute --now "2026-05-17T09:00:00-07:00" --cadence-due-after-days 3 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --execute --manual-trigger-type life_event --manual-trigger-key andrew-kyoto-memory --manual-title "Kyoto memory" --manual-summary "Andrew mentioned a Kyoto memory" --manual-rationale "Manual trip context can become a post" --manual-suggested-next-action "Ask Andrew whether to turn this into a carousel post" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities create --trigger-type new_media --trigger-key processed-2025-kyoto --title "Kyoto night market" --summary "Fresh processed set" --rationale "Enough images for a carousel" --suggested-next-action "Ask Andrew whether to pick 5 photos" --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities list --db data/post_relay.sqlite
.venv/bin/post-relay opportunities dm-plan --opportunity-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities mark-dm-sent --opportunity-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities snooze --opportunity-id 1 --until "2026-05-20T09:30:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities dismiss --opportunity-id 1 --reason "Not now" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities convert-to-draft --opportunity-id 1 --db data/post_relay.sqlite
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

Candidate groups currently use the indexed photo file's parent folder as the first reviewable travel set boundary. During `index scan`, Post Relay now enriches local image records without network calls by reading dimensions plus available EXIF date/camera/lens fields from supported images; unreadable files remain indexed with empty metadata so discovery stays robust. A folder with multiple photos is recommended as a carousel; a one-photo folder is recommended as a single image post. Post records can be created from candidate groups and start in the `drafting` status with placeholder caption/location/hashtag fields. Post preview packages print a stable local review format with ordered included photo paths, unresolved context notes, persisted context questions, and allowed next actions before Discord delivery is added. `drafts artifacts render` creates ordered thumbnails plus two high-DPI PNG review assets under the configured local artifact root and leaves source media unchanged: `contact-sheet-select.png` for Stage 1 selection only, with no crop framing/grid/lead state, and `contact-sheet-crop.png` for Stage 2 crop discussion of the selected subset. `drafts final-preview-artifact render` creates `final-post-preview.png` for Stage 3 approval, using ordered selected media, caption preview, and metadata tags. `drafts media-plan` prints the numbered post media list for contact-sheet review; `drafts media-edit` applies explicit lead/cover, keep/remove, and post-type choices to the underlying candidate media, updates ordering/roles/inclusion, and invalidates active approvals as a material edit. Posts can be submitted for review, approved for queueing, and edited locally; material edits after approval invalidate active approvals and move the post back to `needs_edits`. Dry-run Discord preview payloads reuse the post review text, list ordered existing included image attachment paths, and report missing image files without sending anything. Queue-approved posts can be scheduled, moved into final publish-approval review, and explicitly approved for publishing; this only updates local state and approval records and does not call any live publishing API. The Meta Graph validation command loads tokens only from environment/private `.env`, redacts secrets, uses `graph.facebook.com` by default, and only calls read-only account visibility endpoints. Controlled single-image publish validation requires a `ready_to_publish` `single_image` post, a public HTTPS image URL, and `--execute` before it calls Meta media container or publish endpoints; dry-run mode records a sanitized planned attempt without network calls. Controlled carousel publish validation requires a `ready_to_publish` `carousel` draft and one public HTTPS image URL per selected draft image; execution creates one child media container per image, creates a carousel container from those child ids, polls the carousel container, publishes only when ready, and stores sanitized attempt records. No live carousel smoke test has been run yet. `drafts r2-stage-plan` creates a no-network, no-credential dry-run plan for uploading the ordered draft media and already-generated local review artifacts to the configured temporary R2 staging bucket/domain; object keys are sanitized and do not expose local paths. `drafts r2-stage-upload` remains dry-run by default and only uploads/records planned objects when `--execute` is provided. `drafts r2-cleanup` also defaults to dry-run and, with `--execute`, deletes only SQLite-recorded uploaded objects whose keys remain under the configured Post Relay prefix. R2 remains temporary staging only; local/NAS source media remains the source of truth and is never mutated.

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
