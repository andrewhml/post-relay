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
- Draft records can be created idempotently from candidate groups.
- Draft preview packages can be rendered locally before Discord delivery exists.
- Draft context questions can be generated/listed locally and included in draft previews.
- Draft content direction can be submitted for review, approved for queueing, and invalidated by material edits.
- Dry-run Discord preview payloads can be generated locally with ordered existing image paths and missing-file reporting.
- Local draft review artifacts can be rendered with `drafts artifacts render`; generated thumbnails/contact sheets are written under the configured artifact root without modifying source media.
- Oversized draft review artifact renders are blocked by a bounded planning layer that classifies large media sets and returns DM-safe narrowing/sample guidance before a full contact sheet is rendered.
- DM intake candidate matching uses local folder/year/filename descriptors and simple aliases to prefer specific matched sets over generic large folders while keeping rationale source-path-safe.
- No-network R2 staging plans can be generated with `drafts r2-stage-plan`; plans use sanitized object keys/public URLs, preserve included draft media order, and report missing local files before upload exists.
- R2 staging upload/cleanup can be dry-run locally; `drafts r2-stage-upload --execute` uploads and records planned objects, while `drafts r2-cleanup --execute` deletes only recorded uploaded objects under the configured Post Relay prefix.
- Numbered draft media plans and edits can be applied locally with `drafts media-plan` and `drafts media-edit`; lead/cover, keep/remove, and post-type changes update candidate media ordering/roles/inclusion and invalidate active approvals.
- Local guided draft packages can be generated and accepted with `drafts guided-package-plan`/`drafts guided-package-accept`; accepted packages persist caption, hashtags, confirmed location text, local alt text/accessibility notes, and audited rationale without fabricating unconfirmed facts.
- Local Discord-style X-from-Y photo selection can be modeled without network calls using `drafts discord-selection-plan`/`drafts discord-selection-preview`/`drafts discord-selection-apply`; selection application reuses the same media-selection rules and approval invalidation as `drafts media-edit`.
- Queue-approved drafts can be scheduled locally and moved through final publish approval without live API calls.
- Guarded single-image/carousel publish validation can use either explicit public HTTPS `--image-url` values or recorded uploaded R2 staged media via `--from-staged-r2`, preserving dry-run defaults, double approval, schedule enforcement, and explicit `--execute` publish safeguards.
- Scheduled publish runner preflight can use `meta publish-scheduled --from-staged-r2` to re-check due time, active draft/publish approvals, selected staged R2 media completeness, caption/post type, and safe Meta-bound URLs without network calls before execute mode.
- Final publish preview can use `meta final-publish-preview --from-staged-r2` to render the exact Meta-bound caption, selected staged media URLs, publishable fields, and local/review-only metadata without network calls.
- Publish-ready local exports can be rendered with `drafts publish-exports render`; source media stays immutable, exported files are written under the configured publish export root, mixed-orientation warnings are surfaced, and R2 staging prefers exported publish assets when present.
- Instagram publish capabilities are explicit: media URLs/carousel children, captions, and hashtags-in-caption are publishable; stored hashtags are merged into the caption sent to Meta; alt text, rationale, location ideas, collaborators, music, product/story/reel-only metadata stay local/review-only unless a later milestone validates official support.
- Live Discord delivery should only be added after the local payload harness remains green; next Discord work should be private-DM-first and user-initiated-first. Post Relay now has a no-network `dm intake` harness, live-capable Discord DM selection/guided-review/scheduling/double-confirmed publish approval loops, a local `opportunities` harness, safe local opportunity trigger checks for agent-initiated suggestion records, and DM intake narrowing guardrails for huge weak candidate matches. Do not run live Instagram publish execution from Discord milestones.

## Safety and product constraints

- Never commit secrets or access tokens.
- Never paste tokens into chat or logs.
- Publishing must use official Meta/Instagram routes only.
- Do not use browser automation, password scraping, or unofficial posting methods.
- Treat `graph.facebook.com` as the validated primary Graph route for this account unless a later milestone documents a better supported route.
- Enforce double approval before live publishing:
  1. draft approval
  2. publish approval
- Never implement autonomous live posting without explicit publish approval.
- If a draft changes materially after approval, invalidate prior approvals.

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
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-carousel-publish --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta final-publish-preview --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay meta publish-scheduled --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
# Execute only when due and explicitly authorized in the active session:
.venv/bin/post-relay meta publish-scheduled --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env --execute
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts publish-exports render --draft-id 1 --profile feed_portrait_4x5 --config config/photo_sources.yaml --db data/post_relay.sqlite
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
.venv/bin/post-relay discord dm-publish-approval-apply --draft-id 1 --message "confirm publish approval for draft #1" --discord-channel-id <discord-dm-channel-id> --db data/post_relay.sqlite
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
.venv/bin/post-relay opportunities check --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --execute --now "2026-05-17T09:00:00-07:00" --cadence-due-after-days 3 --db data/post_relay.sqlite
.venv/bin/post-relay opportunities check --execute --manual-trigger-type life_event --manual-trigger-key andrew-kyoto-memory --manual-title "Kyoto memory" --manual-summary "Andrew mentioned a Kyoto memory" --manual-rationale "Manual trip context can become a post" --manual-suggested-next-action "Ask Andrew whether to turn this into a carousel draft" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities create --trigger-type cadence_due --trigger-key weekly-2026-05-17 --title "Weekly posting window" --summary "Queue a reviewed travel set" --rationale "Maintain posting cadence" --next-action "Pick a candidate and create a draft" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities list --db data/post_relay.sqlite
.venv/bin/post-relay opportunities snooze --opportunity-id 1 --until "2026-05-18T09:00:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities dismiss --opportunity-id 1 --reason "not relevant this week" --db data/post_relay.sqlite
.venv/bin/post-relay opportunities convert-to-draft --opportunity-id 1 --db data/post_relay.sqlite
```

## Current next milestone

See `docs/plans/current-agent-roadmap.md`. The first guarded live carousel smoke for draft `2` succeeded; schedule hardening blocks early Meta `--execute`; final publish preview/metadata hardening shows exact Meta-bound captions; and publish export profiles now render 4:5 publish assets before R2 staging. The next planned work is `feat/post-publish-analytics-feedback`. Do not publish another real post before the approved scheduled time unless Andrew explicitly bypasses the schedule in the active session.
