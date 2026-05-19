# Post Relay Agent Handoff

This file is the repo-level handoff for AI agents working on Post Relay.

## Read first

Before making changes, read these files in order:

1. `README.md` — current project status, validated Meta setup facts, local CLI commands.
2. `docs/plans/current-agent-roadmap.md` — current completed milestones, next milestones, and execution rules.
3. `docs/plans/postrelay-agent-operating-baseline.md` — specialized content curator/social media manager prompt and skill baseline.
4. `docs/plans/discord-dm-conversation-orchestration.md` — private-DM-first conversation, user-initiated-first rollout, and later opportunity trigger plan.
5. `docs/plans/discord-photo-selection-before-carousel-smoke.md` — Discord selection/review plan before live carousel publish.
6. `implementation-plan.md` — high-level phase plan from MVP through publishing and optimization.
7. `technical-design.md` — product architecture, safety rules, and component responsibilities.
8. `requirements.md` and `setup-checklist.md` — original requirements and setup notes.

## Project goal

Post Relay is a local-first Instagram travel content workflow for Andrew's `andrewhml` Creator account. It should help turn a processed travel photo backlog into reviewed, scheduled, and eventually published Instagram posts.

## Current architecture direction

- Python package under `src/post_relay/`.
- SQLite database, default local path `data/post_relay.sqlite`.
- CLI entry point: `post-relay`.
- Tests under `tests/`, run with `.venv/bin/python -m pytest -q`.
- Processed Lightroom/year folders are the primary source for the MVP.
- Immich/NAS can be added later as secondary enrichment, not as the v1 source of truth.
- Candidate groups are currently built from indexed photo parent folders.
- Multi-photo folders recommend `carousel`; one-photo folders recommend `single_image`.
- Content artifacts should be called posts throughout user/agent-facing copy; `drafting` is a lifecycle status, not the artifact name. The existing `drafts` CLI namespace remains for backward compatibility; `--post-id` is the primary user-facing option, with `--draft-id` retained as a legacy alias.
- Post records can be created idempotently from candidate groups and start in the `drafting` status.
- Post preview packages can be rendered locally before Discord delivery exists.
- Post context questions can be generated/listed locally and included in post previews.
- Post content direction can be submitted for review, approved for queueing, and invalidated by material edits.
- Dry-run Discord preview payloads can be generated locally with ordered existing image paths and missing-file reporting.
- Local post review artifacts can be rendered in gated stages with `drafts artifacts render --stage select|crop`; generated thumbnails/contact sheets are written under the configured artifact root without modifying source media. Crop artifacts require explicit media selection first for multi-media posts, while single-image/video posts can skip selection and go straight to crop. Final preview artifacts require accepted copy/metadata.
- Oversized post review artifact renders are blocked by a bounded planning layer that classifies large media sets and returns DM-safe narrowing/sample guidance before a full contact sheet is rendered.
- DM intake candidate matching uses local folder/year/filename descriptors and simple aliases to prefer specific matched sets over generic large folders while keeping rationale source-path-safe.
- No-network R2 staging plans can be generated with `drafts r2-stage-plan`; plans use sanitized object keys/public URLs, preserve included post media order, and report missing local files before upload exists.
- R2 staging upload/cleanup can be dry-run locally; `drafts r2-stage-upload --execute` uploads and records planned objects, while `drafts r2-cleanup --execute` deletes only recorded uploaded objects under the configured Post Relay prefix.
- Numbered post media plans and edits can be applied locally with `drafts media-plan` and `drafts media-edit`; lead/cover, keep/remove, and post-type changes update candidate media ordering/roles/inclusion and invalidate active approvals.
- Crop/center feedback can be applied locally with `drafts crop-feedback` using the designed A1-E5 grid vocabulary (`--shift 3:B2`, `--center 5`, `--tighten 6`, `--loosen 9`, `--ratio 3:4:5`); persisted crop edits are rendered in contact sheets/final previews and invalidate active approvals.
- Warm-dark Pillow-rendered contact sheets and final post preview artifacts now follow the `assets/contact sheet/` React/CSS design references; the React files remain design contracts, while CLI/Discord artifacts are static local images.
- Local guided post packages can be generated and accepted with `drafts guided-package-plan`/`drafts guided-package-accept`; accepted packages persist caption, hashtags, confirmed location text, local alt text/accessibility notes, and audited rationale without fabricating unconfirmed facts.
- Local Discord-style X-from-Y photo selection can be modeled without network calls using `drafts discord-selection-plan`/`drafts discord-selection-preview`/`drafts discord-selection-apply`; selection application reuses the same media-selection rules and approval invalidation as `drafts media-edit`.
- Queue-approved posts can be scheduled locally and moved through final publish approval without live API calls.
- Guarded single-image/carousel publish validation can use either explicit public HTTPS `--image-url` values or recorded uploaded R2 staged media via `--from-staged-r2`, preserving dry-run defaults, double approval, schedule enforcement, and explicit `--execute` publish safeguards.
- Scheduled publish runner preflight can use `meta publish-scheduled --from-staged-r2` to re-check due time, durable active content/publish approvals, selected staged R2 media completeness, caption/post type, and safe Meta-bound URLs without network calls before execute mode; final publish approval does not expire after 24 hours and Meta containers are created only when the due runner executes.
- Final publish preview can use `meta final-publish-preview --from-staged-r2` to render the exact Meta-bound caption, selected staged media URLs, publishable fields, and local/review-only metadata without network calls.
- Publish-ready local exports can be rendered with `drafts publish-exports render`; source media stays immutable, exported files are written under the configured publish export root, mixed-orientation warnings are surfaced, and R2 staging prefers exported publish assets when present.
- Instagram publish capabilities are explicit: media URLs/carousel children, captions, hashtags-in-caption, and explicitly resolved Facebook Page `location_id` tags are publishable; stored hashtags are merged into the caption sent to Meta; resolved location tags are stored separately from freeform location text, post-aware candidate review can ask for clarification/search Meta Pages without auto-selecting, and setting a tag requires reapproval; post-publish analytics snapshots capture local published payload outcomes and staged export dimensions without network calls; read-only insights fetch/storage is explicit `--execute` and does not mutate post lifecycle/publish state; recommendation feedback summaries are advisory-only from stored local snapshots/insights and must not mutate posts, approvals, schedules, Discord, R2, or Meta state; follower-growth tracking stores read-only account metric snapshots separately from post lifecycle state and defaults to no-network dry-run; `meta token-extend` dry-runs by default and may exchange/update the private `.env` token only with explicit `--execute --update-env` while redacting secrets; alt text, rationale, freeform location text/ideas, collaborators, music, product/story/reel-only metadata stay local/review-only unless a later milestone validates official support.
- Live Discord delivery should only be added after the local payload harness remains green; next Discord work should be private-DM-first and user-initiated-first. Post Relay now has a no-network `dm intake` harness, a no-network `dm next-action` planner that includes all locally scheduled posts before suggesting another slot, live-capable Discord DM selection/guided-review/scheduling/final publish approval loops, a local `opportunities` harness, safe local opportunity trigger checks for agent-initiated suggestion records, proactive opportunity DM plans and mark-sent controls, and DM intake narrowing guardrails for huge weak candidate matches. Do not run live Instagram publish execution from Discord milestones.

## Safety and product constraints

- Never commit secrets or access tokens.
- Never paste tokens into chat or logs.
- Publishing must use official Meta/Instagram routes only.
- Do not use browser automation, password scraping, or unofficial posting methods.
- Treat `graph.facebook.com` as the validated primary Graph route for this account unless a later milestone documents a better supported route.
- Enforce double approval before live publishing:
  1. content approval while the post is in/reviewed from `drafting`
  2. publish approval
- Never implement autonomous live posting without explicit publish approval.
- If a post changes materially after approval, invalidate prior approvals.

## Workflow rules for agents

- Use rollback-safe milestone branches and PRs.
- Start every milestone from synced `main`.
- Use branch names like `feat/draft-records-from-candidates`, `docs/agent-roadmap`, or `fix/...`.
- Keep one milestone per PR.
- Use TDD for code changes:
  1. write failing tests first
  2. run the focused test and confirm it fails for the expected reason
  3. implement the minimum code
  4. run focused tests
  5. run the full suite
- For integration-like features such as Discord messaging or image previews, add narrow check-in tests before building the full integration. Prefer local/dry-run payload tests from a fixture photo directory before live Discord delivery.
- For docs-only changes, still run the existing test suite before merging.
- Squash merge PRs to `main`, delete the feature branch, then sync local `main` before starting another milestone.

## Useful commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/post-relay db init --db data/post_relay.sqlite
.venv/bin/post-relay index scan --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay library stats --db data/post_relay.sqlite
.venv/bin/post-relay meta validate-readonly --env-file .env --dry-run
.venv/bin/post-relay meta token-extend --env-file .env
.venv/bin/post-relay meta token-extend --env-file .env --execute --update-env
.venv/bin/post-relay meta validate-image-publish --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-carousel-publish --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta final-publish-preview --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay meta publish-scheduled --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
# Execute only when due and explicitly authorized in the active session:
.venv/bin/post-relay meta publish-scheduled --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env --execute
.venv/bin/post-relay analytics snapshot --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay analytics insights-plan --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay analytics insights-fetch --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay analytics feedback-summary --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay analytics feedback-summary --limit 10 --db data/post_relay.sqlite
.venv/bin/post-relay analytics follower-fetch --instagram-account-id 17841400498120050 --db data/post_relay.sqlite
.venv/bin/post-relay analytics follower-summary --target-followers 5000 --db data/post_relay.sqlite
# Execute only for read-only insights collection when the token has instagram_manage_insights:
.venv/bin/post-relay analytics insights-fetch --post-id 1 --metric reach --metric likes --metric comments --metric saved --metric shares --db data/post_relay.sqlite --env-file .env --execute
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --post-id 1 --stage select --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-edit --post-id 1 --lead 3 --keep 1,3,5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --post-id 1 --stage crop --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts crop-feedback --post-id 1 --shift 3:B2 --center 5 --tighten 6 --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-plan --post-id 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-accept --post-id 1 --caption-index 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts final-preview-artifact render --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts publish-exports render --post-id 1 --profile feed_portrait_3x4 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts location-candidates --post-id 1 --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay drafts location-candidates --post-id 1 --query "Gwangjang Market Seoul" --env-file .env --db data/post_relay.sqlite
.venv/bin/post-relay drafts location-tag-set --post-id 1 --page-id <facebook-page-location-id> --name "Seoul, Korea" --source pages/search --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-plan --post-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-preview --post-id 1 --target-count 5 --artifact-path data/review_artifacts/draft-1/contact-sheet-select.png --db data/post_relay.sqlite
.venv/bin/post-relay drafts discord-selection-apply --post-id 1 --select 3,1,5,7,8 --lead 3 --target-count 5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay dm intake --message "start a post about Kyoto night market" --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay dm next-action --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay dm next-action --post-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay dm intake --message "make this cinematic and less touristy" --post-id 1 --discord-channel-id dm-andrew --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-send --post-id 1 --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-poll --post-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --target-count 5 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-selection-apply --post-id 1 --message "select 3,1,5,7,8 lead 3" --target-count 5 --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-guided-review-send --post-id 1 --mood cinematic --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-guided-review-poll --post-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-guided-review-apply --post-id 1 --message "location: Seoul, South Korea; story: night market alleys; mood: cinematic; hook: food and light; caption 1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-schedule-send --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-schedule-poll --post-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-schedule-apply --post-id 1 --message "slot 1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-send --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-poll --post-id 1 --channel-id <discord-dm-channel-id> --after-message-id <prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-poll --post-id 1 --channel-id <discord-dm-channel-id> --after-message-id <confirmation-prompt-message-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-apply --post-id 1 --message "confirm publish approval for post #1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay discord dm-publish-approval-apply --post-id 1 --message "confirm publish approval for post #1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-plan --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute --reason "publish complete"
.venv/bin/post-relay drafts discord-preview --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts submit --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --post-id 1 --approved-by andrew --notes "Content direction approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts edit --post-id 1 --caption "Draft caption" --db data/post_relay.sqlite
.venv/bin/post-relay drafts schedule --post-id 1 --scheduled-for "2026-05-05T09:30:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve-publish --post-id 1 --approved-by andrew --notes "Final approval" --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions generate --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions list --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --execute --now "2026-05-17T09:00:00-07:00" --cadence-due-after-days 3 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --execute --manual-trigger-type life_event --manual-trigger-key andrew-kyoto-memory --manual-title "Kyoto memory" --manual-summary "Andrew mentioned a Kyoto memory" --manual-rationale "Manual trip context can become a post" --manual-suggested-next-action "Ask Andrew whether to turn this into a carousel post" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities create --trigger-type cadence_due --trigger-key weekly-2026-05-17 --title "Weekly posting window" --summary "Queue a reviewed travel set" --rationale "Maintain posting cadence" --next-action "Pick a candidate and create a draft" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities list --db data/post_relay.sqlite
.venv/bin/post-relay opportunities dm-plan --opportunity-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities mark-dm-sent --opportunity-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities snooze --opportunity-id 1 --until "2026-05-18T09:00:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities dismiss --opportunity-id 1 --reason "not relevant this week" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities convert-to-draft --opportunity-id 1 --db data/post_relay.sqlite
```

## Current next milestone

See `docs/plans/current-agent-roadmap.md`. The first guarded live carousel smoke for draft `2` succeeded; schedule hardening blocks early Meta `--execute`; final publish preview/metadata hardening shows exact Meta-bound captions and hashtags embedded in the caption payload; publish export profiles render 4:5 publish assets before R2 staging; `feat/location-tag-validation` validated official Meta Graph `location_id` support for explicitly selected Facebook Page locations; post-publish analytics, read-only insights, recommendation feedback summaries, follower-growth tracking, token extension, DM next-action planning, durable scheduled publish approvals, and the warm-dark chat artifact refresh are implemented. PR #64 / `feat/contact-sheet-design-v2` landed and Andrew validated those Stage 1/2/3 assets in Discord with the upcoming post. PR #65 / `feat/dm-operating-loop-hardening` made the next-action planner first-class around the Stage 1/2/3 artifact loop. PR #66 / `feat/proactive-opportunity-dm-controls` added local `opportunities dm-plan` and `opportunities mark-dm-sent` controls so agent-initiated suggestions remain operator-approved and no-network until Andrew explicitly authorizes a live Discord send. Current PR #67 / `feat/local-media-discovery-enrichment` adds no-network `index scan` enrichment for local image dimensions plus available EXIF date/camera/lens metadata; then choose from video/reel validation or generated/perceptual local narrowing. Use `analytics feedback-summary` plus `analytics follower-summary` as advisory baselines when planning reviewed posts. Freeform `location_text` remains local/review-only and must not be sent as a Meta location tag. Do not publish another real post before the approved scheduled time unless Andrew explicitly bypasses the schedule in the active session.
