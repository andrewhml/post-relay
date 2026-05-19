# Current Agent Roadmap Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task when a milestone is large enough to delegate. Use one rollback-safe branch and PR per milestone.

**Goal:** Make the Post Relay plan discoverable and executable for future agents across sessions.

**Architecture:** Post Relay is a local-first Python CLI and SQLite workflow. The repo now supports processed-folder indexing, candidate/draft creation, numbered media selection, crop/center feedback, warm-dark local review artifacts, final post preview artifacts, R2 staging, guarded single-image/carousel publish validation, private Discord DM intake/selection/guided review/scheduling/double-confirmed final approval, local opportunity records, safe opportunity trigger checks, DM narrowing guardrails, bounded review artifact planning, semantic local candidate matching, Instagram-optimized export assets, and resolved Meta location tags. The first live carousel smoke succeeded; schedule enforcement, final Meta-bound caption/metadata preview, export profiles, guarded `location_id` support, advisory analytics/follower summaries, and contact-sheet chat artifact refresh are now in place.

**Tech Stack:** Python 3.9+, SQLite, Typer, Pydantic, PyYAML, Pillow, pytest, GitHub PR milestone workflow.

---

## Source of truth docs

Future agents should read these files before implementing:

1. `AGENTS.md`
2. `README.md`
3. `docs/plans/current-agent-roadmap.md`
4. `docs/plans/postrelay-agent-operating-baseline.md`
5. `docs/plans/discord-dm-conversation-orchestration.md`
6. `docs/plans/discord-photo-selection-before-carousel-smoke.md`
7. `implementation-plan.md`
8. `technical-design.md`
9. `requirements.md`
10. `setup-checklist.md`

If these files conflict, prefer the newest concrete implementation facts in `README.md`, `AGENTS.md`, and this roadmap, then reconcile by updating docs in the same PR.

## Completed milestones

### PR #2 / earlier: Python SQLite scaffold

Implemented:
- Python package under `src/post_relay/`
- SQLite schema initialization
- tests and pytest setup
- local Python venv workflow

### PR #3: Draft workflow state model

Implemented:
- `src/post_relay/state.py`
- `DraftState` enum matching the double-approval workflow
- `ApprovalType` enum with `draft` and `publish`
- guarded `transition_draft_state(...)`
- tests preventing unsafe jumps to publishing

Important behavior:
- Posting can only happen from `ready_to_publish`.
- Material edits can move approved/scheduled drafts back to `needs_edits`.

### PR #4: Candidate group builder

Implemented:
- `src/post_relay/candidates.py`
- repository methods for candidate group creation/listing
- candidate build/list CLI commands
- candidate group idempotency by `(source_name, source_folder)`
- README updates with current CLI commands

Important behavior:
- Candidate groups currently use the indexed photo file's parent folder as the review boundary.
- Example: `processed/2023/kyoto/temple.jpg` and `processed/2023/kyoto/garden.jpg` become candidate group `2023 / kyoto`.
- Multi-photo folders recommend `carousel`.
- One-photo folders recommend `single_image`.

### PR #6: Draft records from candidates

Implemented:
- `src/post_relay/drafts.py`
- repository methods for draft creation/listing
- `drafts create` and `drafts list` CLI commands
- idempotent one-draft-per-candidate behavior
- tests for draft persistence, idempotency, missing candidates, and CLI flow

Important behavior:
- `drafts create --candidate-id N` requires an existing candidate group.
- Draft records inherit `post_type` from the candidate group's recommendation.
- Initial draft status is `drafting` from the workflow state model.
- Caption, hashtags, location, and alt text are intentionally empty placeholders for later drafting/review milestones.

### PR #7: Draft review package

Implemented:
- `src/post_relay/review_package.py`
- repository methods for retrieving a draft and ordered candidate photo file paths
- `drafts preview` CLI command
- stable local text review package rendering
- tests for package content, formatting, missing drafts, and CLI flow

Important behavior:
- `drafts preview --draft-id N` requires an existing draft.
- Preview output includes draft id, status, candidate title, post type, ordered photo file paths, placeholders for caption/location/hashtags/alt text, unresolved context notes, and allowed next actions.
- Empty caption/location/hashtags/alt text are rendered as explicit `<empty>` placeholders.
- Photo paths are ordered by candidate group item sort order.

### PR #8: Context placeholders and questions

Implemented:
- `src/post_relay/context_questions.py`
- `context_questions` SQLite table
- repository methods for creating/listing context questions
- `drafts questions generate` and `drafts questions list` CLI commands
- draft preview integration for persisted unresolved context questions
- tests for context question generation, idempotency, missing drafts, preview integration, and CLI flow

Important behavior:
- Context question generation is idempotent by `(draft_id, field_name)`.
- Generated starter questions cover place, trip name, approximate date, mood, and story angle.
- Approximate-date wording uses the candidate source year when available.
- Draft previews include persisted unresolved context questions in addition to placeholder notes.
- Discord/image preview work should be built behind narrow check-in tests using local fixture photo directories before live Discord delivery.

### PR #9: Draft approval CLI

Implemented:
- `src/post_relay/approvals.py`
- approval repository helpers for active approval listing and invalidation
- draft content/status update helpers
- `drafts submit`, `drafts approve`, and `drafts edit` CLI commands
- approval invalidation columns on the `approvals` table, with lightweight migration support for existing local databases
- tests for review submission, approval persistence, approval state guards, material edit invalidation, missing drafts, and the CLI flow

Important behavior:
- `drafts submit --draft-id N` moves `drafting` or `needs_edits` drafts to `awaiting_review` through the guarded state model.
- `drafts approve --draft-id N` requires `awaiting_review`, records an approval with type `draft`, and moves the draft to `approved_for_queue`.
- `drafts edit --draft-id N` can update caption, hashtags, location, and alt text placeholders.
- Material edits after an active approval invalidate active approvals and move the draft to `needs_edits`.
- This milestone still does not schedule or publish; publish approval remains a later, separate approval type.

### PR #10: Discord preview payload harness

Implemented:
- `src/post_relay/discord_preview.py`
- `DiscordPreviewPayload` model for dry-run delivery payloads
- `drafts discord-preview` CLI command
- tests for ordered existing image paths, missing image reporting, stable dry-run rendering, missing drafts, and CLI smoke behavior

Important behavior:
- `drafts discord-preview --draft-id N` builds a dry-run payload only; it does not call Discord or any external messaging API.
- Payload message text reuses the local draft review package, so Discord-facing text stays aligned with `drafts preview`.
- Payload image attachments preserve candidate item order and include only files that still exist locally.
- Missing image files are reported separately and make `ready_to_send` false so live delivery can be blocked later.
- This is the check-in harness required before live Discord message delivery.

### PR #11: Schedule and publish approval CLI

Implemented:
- `src/post_relay/scheduling.py`
- repository helper for setting `scheduled_for` while updating draft status
- `drafts schedule`, `drafts request-publish-approval`, and `drafts approve-publish` CLI commands
- tests for scheduling guards, scheduled state persistence, publish approval request, final publish approval persistence, missing drafts, and CLI flow

Important behavior:
- `drafts schedule --draft-id N --scheduled-for ...` requires `approved_for_queue`, sets `scheduled_for`, and moves the draft to `scheduled`.
- `drafts request-publish-approval --draft-id N` requires `scheduled` and moves the draft to `awaiting_publish_approval`.
- `drafts approve-publish --draft-id N` requires `awaiting_publish_approval`, records an approval with type `publish`, and moves the draft to `ready_to_publish`.
- This milestone does not call Meta, Discord, or any external publishing API; it only prepares the local state and audit trail.
- Draft approval and publish approval remain separate active approval records unless a material edit invalidates them.

### PR #12: Meta Graph client readonly

Implemented:
- `src/post_relay/meta_graph.py`
- `MetaGraphConfig` and `.env`/environment loader for Meta Graph settings
- token/app-secret redaction helper for safe errors and summaries
- injectable read-only Meta Graph client transport for tested account validation without live calls
- `meta validate-readonly` CLI command with `--dry-run` for sanitized planned requests
- `.env.example` entries for Graph base URL and API version
- tests for config loading, environment precedence, missing token errors, redaction, read-only request construction, sanitized request errors, and CLI dry-run output

Important behavior:
- `POST_RELAY_USER_ACCESS_TOKEN` is required for validation and is loaded only from environment or private `.env` files.
- Environment variables override `.env` values.
- Default route remains `https://graph.facebook.com`.
- The client only calls read-only visibility endpoints: `/me/accounts`, the configured/visible Page with `instagram_business_account`, and the linked Instagram account fields.
- Tokens are included in requests but redacted from summaries, CLI dry-run output, and wrapped request errors.

### PR #13: Controlled single-image publish validation

Implemented:
- `src/post_relay/publishing.py`
- `publish_attempts` SQLite table for sanitized publish validation audit records
- Meta Graph client helpers for image media container creation, container status polling, and media publishing
- `meta validate-image-publish` CLI command with safe default dry-run behavior unless `--execute` is passed
- tests for draft readiness guards, unsupported non-single-image drafts, sanitized dry-run attempt logging, Graph request sequence, draft state updates, and CLI dry-run behavior

Important behavior:
- Controlled image publish validation only supports `single_image` drafts that have reached `ready_to_publish` through the double-approval workflow.
- The command requires a public HTTPS `--image-url`; local files are not uploaded directly to Meta in this milestone.
- Dry-run mode records a sanitized planned attempt and explicitly calls no Meta publishing endpoints.
- Live execution requires `--execute`, loads credentials only from environment/private `.env`, creates an image container, checks `status_code`, publishes only when the container is `FINISHED`, stores the container/media ids, and moves the draft to `posted` on success.
- Failure paths store sanitized error messages and move the draft to `failed`; access tokens and secret-like image URL query values are not stored in attempt records.

### PR #17: Live single-image publish smoke test

Observed on 2026-05-03:
- Andrew provided a fresh private Meta Graph user access token and public HTTPS smoke-test image URL in local `.env`.
- Read-only validation succeeded for Page `Andrewhml` (`998312870038313`) and linked Instagram account `andrewhml` (`17841400498120050`), with media count `206` and no publishing endpoints called.
- Live read-only validation showed the Instagram account endpoint does not support the `account_type` field for this app/API combination; Post Relay now requests only `id,username,media_count` and renders account type as `<unknown>`.
- The first live publish attempt failed before creating a container because Post Relay used GET for media container creation; Meta did not return a container id. The failed local DB was archived as `data/post_relay.failed-get-publish-attempt.sqlite` for debugging only and is ignored by git.
- After fixing publish requests to use POST for `/{ig-user-id}/media` and `/{ig-user-id}/media_publish`, the explicit live smoke test succeeded.
- Published smoke-test result: container id `18585234496016605`, container status `FINISHED`, published media id `18085108061165756`, local draft status `posted`.
- The caption value in local `.env` was not used for the live post; the publish path uses the approved draft caption stored in SQLite. This is acceptable for the long-term workflow because `.env` should only provide credentials/configuration, not canonical post content.
- Full local test suite remained `57 passed` after the smoke-test fixes.

### Current milestone: Carousel publish support

Implemented:
- `meta validate-carousel-publish` CLI command with dry-run planning by default and live execution only behind `--execute`
- Meta Graph client helpers for carousel child container creation and carousel parent container creation
- `publish_attempts` audit columns for sanitized ordered image URL lists and ordered child container ids
- local runbook at `docs/publishing/carousel-smoke-test.md`
- tests for sanitized dry-run attempts, guarded ready-to-publish carousel requirements, request method/order/params, draft state updates, and CLI dry-run output

Important behavior:
- Carousel validation requires a `ready_to_publish` `carousel` draft with a non-empty approved draft caption.
- The command requires one public HTTPS `--image-url` per selected draft image and rejects mismatched counts.
- Dry-run mode records a sanitized planned attempt and explicitly calls no Meta publishing endpoints.
- Live execution creates one child container per image with `is_carousel_item=true`, creates a parent carousel container with `media_type=CAROUSEL` and ordered child ids, polls the carousel container, publishes only after `FINISHED`, and moves the draft to `posted` only after Meta returns a published media id.
- Failure paths store sanitized errors and move the draft to `failed`; access tokens and secret-like image URL query values are not stored in attempt records.
- No live carousel publish smoke test has been run yet.

## Current local verification command

Run this before opening or merging any PR:

```bash
.venv/bin/python -m pytest -q
```

Expected current result after the local media discovery enrichment milestone:

```text
254 passed
```

## Milestone execution rules

Use this process for every milestone:

1. Start from clean synced `main`.

   ```bash
   git checkout main
   git pull --ff-only origin main
   git checkout -b <milestone-branch>
   ```

2. For code milestones, use TDD:
   - write focused failing tests first
   - run the focused tests and verify the expected failure
   - implement the minimum code
   - run focused tests
   - run the full suite
   - for integration-like features, add check-in tests at each seam before live external calls; for Discord/image previews, verify local fixture-directory payloads and image path ordering before sending messages

3. Commit with a conventional commit message.

4. Push and open a PR.

5. Verify local tests pass.

6. Squash merge the PR and delete the branch.

7. Sync local `main` before starting the next milestone.

Do not accumulate multiple product milestones in one long-lived branch.

## Product and safety invariants

Agents must preserve these unless Andrew explicitly changes the product direction:

- Human-in-the-loop review is mandatory.
- Live publishing requires double approval:
  1. draft approval
  2. publish approval
- Any material draft/media change after approval invalidates prior approval.
- Use official Meta/Instagram APIs only.
- No browser automation, password scraping, or unofficial posting.
- Do not log or commit tokens/secrets.
- The validated Graph API route for this account is `graph.facebook.com`; `graph.instagram.com` previously returned `Invalid platform app`.
- The MVP source of truth is processed local Lightroom/year folders.
- Immich/NAS integration is later enrichment, not v1 authority.
- Stories are mostly manual for now.
- Reels are later experiments unless explicitly validated.
- Feed/carousel workflows are the early publishing target.

## Implemented roadmap milestones

### Milestone 1: `feat/content-pipeline-config` (completed in PR #21)

**Goal:** Configure the durable content pipeline shape: local processed folders, NAS processed folders, local review-artifact settings, and disabled-by-default Cloudflare R2 staging settings.

**Reference plan:** `docs/plans/content-pipeline-r2-staging-plan.md`

**Preconditions:**
- Local and NAS folders remain the source of truth.
- Post Relay must never delete, move, or mutate original local/NAS media.
- R2 is temporary staging/review delivery only, not canonical storage.
- R2 secrets must be loaded only from private `.env` or environment variables.

**Expected behavior:**
- Config examples document local and NAS processed-folder sources, currently `/Volumes/Media/photos/2024 Photos/Processed` and `/Users/andrewlee/Pictures/2025 Photos/Processed`.
- Config models include review artifact and R2 staging sections.
- R2 staging is disabled by default and requires no credentials unless a staging command needs them; current bucket/public route is `post-relay-publish` via `https://peddocks.net`.
- Tests cover config parsing and no-secret rendering.

### Milestone 2: `feat/review-artifact-generation` (completed in PR #22)

**Goal:** Generate local thumbnails/contact sheets for draft review without modifying source files.

**Expected behavior:**
- Review artifacts are written under a configured local artifact root.
- Ordered draft media paths produce ordered thumbnails and contact sheets.
- Contact sheets include the draft id and candidate title header.
- Originals are opened read-only and never deleted or modified.
- CLI rendering rejects artifact roots that overlap configured photo source roots.
- `drafts artifacts render --draft-id N --config ... --db ...` prints the local artifact paths for review handoff.

### Milestone 3: `feat/r2-staging-dry-run` (completed in PR #23)

**Goal:** Produce a safe no-network R2 staging plan for draft media and review artifacts.

**Implemented:**
- `src/post_relay/r2_staging.py` no-network planner for draft media and already-rendered local review artifacts
- `drafts r2-stage-plan` CLI command
- tests for sanitized object keys/public URLs, missing local/NAS file reporting, carousel order preservation, config validation, missing drafts, and CLI dry-run output

**Important behavior:**
- Object keys are derived from draft id, item role, item order, and sanitized filenames; local absolute paths are never embedded in object keys.
- Dry-run output prints planned public HTTPS URLs under the configured R2 public base URL and prefix.
- Missing source files are reported in the plan and make `ready_to_upload` false before any upload feature exists.
- Carousel media order is preserved from candidate group item order.
- The command makes no network calls and does not require R2 credentials.

### Milestone 4: `feat/draft-media-selection` (completed in PR #24)

**Goal:** Let Andrew explicitly translate numbered contact-sheet review feedback into local draft media selection before Discord natural-language handling exists.

**Implemented:**
- `src/post_relay/media_selection.py` service for numbered draft media plans and explicit media edits
- `drafts media-plan` CLI command for showing numbered review media, roles, inclusion status, and edit examples
- `drafts media-edit` CLI command for `--lead`, `--keep` or `--remove`, and optional `--post-type single_image|carousel|reel`
- repository helpers for reading/updating candidate media item role, inclusion status, and sort order
- tests for lead-first ordering, keep/remove validation, single-image/carousel guards, approval invalidation, included-only downstream previews/staging, and CLI output

**Important behavior:**
- Review numbers come from current candidate media sort order, matching contact sheet/review presentation.
- The lead/cover photo becomes the first included item and receives role `primary`; other included media are `support`.
- Removed media are retained in SQLite as `include_status = 'excluded'`; source media is never moved/deleted/mutated.
- Material media edits invalidate active approvals and move approved/scheduled/ready drafts back to `needs_edits` through the guarded state model.
- Draft preview, Discord preview, R2 staging plans, and publish image-count validation use included media only, preserving the revised order.
- `reel` is accepted as local post-type intent only; live reel publishing remains unvalidated future work.

### Milestone 5: `feat/r2-staging-upload-and-cleanup` (completed in PR #25)

**Goal:** Upload Post Relay-created staging objects to R2 and clean up only those staged objects after publish/cancellation/explicit cleanup.

**Implemented:**
- `src/post_relay/r2_staging_upload.py` service for guarded R2 upload and cleanup with an injectable storage-client seam
- `r2_staged_objects` SQLite table plus repository helpers for uploaded/deleted staged object audit records
- `drafts r2-stage-upload` CLI command, dry-run by default and uploading only with `--execute`
- `drafts r2-cleanup` CLI command, dry-run by default and deleting only recorded uploaded objects with `--execute`
- tests for no-network dry runs, execute-mode upload records, missing-source blocking, recorded-object cleanup, configured-prefix safety refusal, and CLI dry-run output

**Important behavior:**
- Upload and deletion require explicit `--execute`; default CLI behavior makes no network calls and writes no upload/cleanup records.
- Upload execution uses the existing R2 staging plan, refuses missing source files before any upload, then records only successfully planned objects in SQLite.
- Cleanup reads uploaded records from SQLite and refuses to delete records whose bucket/prefix no longer match the configured Post Relay staging scope.
- Cleanup never touches local/NAS source paths; it only calls R2 object deletion for recorded staged object keys.
- R2 credentials are read only from environment variables named by config in execute mode; dry runs do not require credentials.
- Failed publishes should leave uploaded staged records available until explicit cleanup.

### Milestone 6: `feat/publish-from-staged-r2` (completed in PR #26)

**Goal:** Let Meta publish validation use staged R2 HTTPS URLs for single-image and carousel drafts.

**Implemented:**
- `resolve_staged_r2_publish_image_urls(...)` for resolving uploaded `draft_media` R2 records into ordered public HTTPS publish URLs
- `--from-staged-r2` and `--config` support on `meta validate-image-publish` and `meta validate-carousel-publish`
- tests for single-image resolution, carousel order preservation, missing staged-media blocking, sanitized dry-run attempt recording, and CLI dry-run flow

**Important behavior:**
- Existing double-approval and `--execute` publish guards remain unchanged.
- Manual `--image-url` mode still works; `--from-staged-r2` is mutually exclusive with explicit `--image-url` values.
- URL resolution uses currently selected draft media order, matches uploaded R2 records by local source path, filters to uploaded `draft_media` objects in the configured bucket/prefix/public base URL, and ignores staged artifacts such as contact sheets.
- Dry runs sanitize staged R2 URL query secrets in publish attempt records and output while making no Meta publishing calls.
- Successful publish moves the draft to `posted`; staged records remain uploaded so `drafts r2-cleanup --execute --reason "publish complete"` can delete only recorded app-created objects.
- Failed publish keeps staged objects available until explicit cleanup.

### Milestone 7: `feat/discord-selection-model` (completed in PR #31)

**Goal:** Add a local, testable model for Andrew to select X photos from Y suggested draft photos before any live carousel smoke test.

**Reference plan:** `docs/plans/discord-photo-selection-before-carousel-smoke.md`

**Implemented:**
- `src/post_relay/discord_selection.py` service for rendering local Discord-style X-from-Y selection requests and applying ordered selections
- `drafts discord-selection-plan` CLI command for dry-run selection-request text with numbered suggested media and lead/cover guidance
- `drafts discord-selection-apply` CLI command for applying Andrew's selected numbers, target count, lead/cover, and optional post type locally
- tests for request rendering, target-count validation, duplicate/wrong-count/lead validation, approval invalidation, downstream preview ordering, and CLI harness output

**Important behavior:**
- The milestone makes no Discord, R2, or Meta network calls.
- Selection requests use the current draft media review order and show X/Y counts plus command fallback semantics.
- Applying selection delegates to the existing media-selection service so lead-first ordering, primary/support roles, included/excluded status, post-type guards, and approval invalidation stay consistent with `drafts media-edit`.
- Carousel target counts require 2-10 photos; single-image target counts require exactly one photo.
- The next milestone remains dry-run only: `feat/discord-selection-payload`.

### Milestone 8: `feat/discord-selection-payload` (completed in PR #32)

**Goal:** Extend the dry-run Discord payload harness so Andrew can preview a "select X from Y" request locally before live bot delivery.

**Implemented:**
- `DiscordSelectionPayload` dry-run payload model for numbered X-from-Y selection requests
- `build_discord_selection_payload(...)` for preserving suggested draft media order, reporting missing source media, and including optional local artifact references
- `drafts discord-selection-preview` CLI command for rendering the dry-run payload without sending Discord messages
- tests for interaction semantics, ordered image attachments, artifact references, missing media/artifact reporting, and CLI output

**Important behavior:**
- The command explicitly says no Discord messages were sent.
- Payload text includes exact interaction semantics: accept exactly X selected numbers, require lead/cover inside the selection, preserve Andrew's selected order, and reject incomplete/duplicate/out-of-range choices.
- Missing source images or missing local artifacts make `ready_to_send` false in the dry-run output.
- Fallback notes document contact sheets, thumbnail/local artifact paths, source paths, and staged review media as later options if Discord attachments are unreliable.
- The next no-network milestone is `feat/discord-guided-draft-package`; live Discord bot testing should wait until Andrew reviews this payload shape.

### Milestone 9: `feat/discord-guided-draft-package` (completed in PR #33)

**Goal:** Add a local, testable guided drafting service that turns selected media plus Andrew's answers into a complete growth-oriented post package.

**Delivered behavior:**
- Added `drafts guided-package-plan` and `drafts guided-package-accept` as no-network CLI harnesses.
- Recommends `single_image`, `carousel`, or `reel-planning-only` from the selected/included media count and current draft type.
- Generates focused context questions for missing location, story angle, mood, audience hook, include, and avoid fields.
- Produces three hook-first caption options, hashtag suggestions, confirmed location text when provided, local alt text/accessibility notes, and a follower-growth rationale.
- Does not invent missing location/date/event facts; missing facts remain explicit questions for Andrew.
- Acceptance persists the chosen caption, hashtags, confirmed location text, alt text, and an audited guided package record in SQLite.

**Safety notes:**
- No Discord, R2, or Meta network calls.
- Local alt text and rationale are stored for review/approval, not assumed publishable through Meta until the capability matrix milestone validates fields.

### Milestone 10: `feat/instagram-capability-matrix` (completed in PR #34)

**Goal:** Make Post Relay explicit about which Instagram post fields it can publish programmatically and which remain local/review-only.

**Delivered behavior:**
- Added `src/post_relay/instagram_capabilities.py` as the explicit publish capability matrix.
- Marks media URLs/carousel children, approved caption text, and hashtags embedded in captions as publishable in the validated v1 Graph path.
- Marks local alt text/accessibility notes, growth/schedule rationale, location ideas, collaborators, product tags, story fields, reel fields, music, and unknown future fields as review-only, needs-validation, or unsupported v1.
- Discord selection preview output includes capability notes so Andrew can see which metadata is publishable versus local/manual.
- Publish validation tests assert review-only metadata is not sent to Meta media or carousel container requests.

**Safety notes:**
- No new live Meta, Discord, or R2 network calls.
- Unsupported metadata remains local/review-only until a future official capability validation milestone changes the matrix.
- Publish attempts remain sanitized and only include the already-validated media/caption fields.

### Milestone 11: `feat/postrelay-agent-operating-baseline` (completed in PR #36)

**Goal:** Define the specialized content curator/social media manager baseline before building live DM behavior.

**Reference plan:** `docs/plans/postrelay-agent-operating-baseline.md`

**Delivered behavior:**
- Documented the Post Relay agent role as a specialized content curator and social media manager for Andrew's `andrewhml` travel photography account.
- Captured the baseline prompt and focused skill areas: media curation, guided post packages, factuality/sensitivity, Instagram capability checks, scheduling/growth cadence, approval safety, and private-DM conversation management.
- Made the rollout order explicit: user-initiated DM post creation first; agent-initiated suggestions only after that loop is working effectively and proven.
- Did not call Discord, R2, or Meta services in this milestone.

### Milestone 12: `feat/discord-dm-user-intake-harness`

**Goal:** Add a no-network harness that turns Andrew's private-DM-style text into a user-initiated post conversation or draft-context update.

**Delivered behavior:**
- Added a `conversation_threads` SQLite table for local DM conversation state and a `conversation_context_notes` table for sanitized durable context notes.
- Added `src/post_relay/dm_intake.py` for user-initiated private-DM-style intake without Discord network calls.
- Added `post-relay dm intake --message ...` as a CLI harness that can start/reuse a user-initiated DM thread, suggest matching candidate groups, or attach sanitized context to an active draft.
- DM-facing copy gives concise next options and avoids local absolute paths, secrets, and raw token-like values.
- Agent-initiated opportunities, live Discord sends, and Meta publishing calls remain out of scope.

**Safety notes:**
- The harness is local-only/no-network.
- It stores sanitized summaries rather than raw Discord transcript logs.
- It routes draft-linked context to media selection as the next safe step; later milestones can route to guided package, scheduling, or approvals once live DM selection/review is implemented.

### Milestone 13: `feat/discord-dm-selection-bot` (completed in PR #38)

**Goal:** Let Andrew interact with the live Discord bot in a private DM to choose X photos from Y suggestions and persist the choice into draft media selection.

**Delivered behavior:**
- Added `src/post_relay/discord_dm.py` with a live-capable private DM adapter for selection prompts, reply polling, DM-friendly reply parsing, and confirmation messages.
- Added `post-relay discord dm-selection-send` to create Andrew's private DM channel through Discord's REST API, send a selection prompt, and record/update a local conversation thread.
- Added `post-relay discord dm-selection-poll` to poll a private DM after the prompt message, apply the first parseable Andrew-authored selection reply, and send a confirmation back to the same DM.
- Added `post-relay discord dm-selection-apply` as a no-network command fallback for applying a copied DM reply locally.
- Reused the existing local selection service so final included ordering, lead/cover, excluded photos, and approval invalidation match `drafts discord-selection-apply`/`drafts media-edit` behavior.
- Added environment-only Discord bot configuration via `POST_RELAY_DISCORD_BOT_TOKEN` and `POST_RELAY_DISCORD_TARGET_USER_ID`; no secrets are committed or printed.
- Added fake-transport and CLI tests for private DM prompt sending, reply parsing, polling, confirmation output, REST message listing, and no-network fallback application.

**Safety notes:**
- Discord credentials are read only from environment/private `.env` equivalents and are redacted from errors/output.
- DM-facing selection text avoids local absolute source paths and token-like values.
- The live-capable commands are Discord-only for this milestone; no Meta publishing endpoints are called.
- A real Discord-only private DM smoke test can be run after credentials are configured, but live Instagram publish execution remains deferred.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_discord_dm.py -q
.venv/bin/python -m pytest -q
```

Current local result: `129 passed`.

### Milestone 14: `feat/discord-dm-guided-review`

**Goal:** Expand private DM conversations from media selection into guided post-building for post type, content, metadata, and accepted content decisions before scheduling/approval guidance.

**Current branch progress (draft PR #39):**
- Added a no-network `discord dm-guided-review-apply` harness that parses DM-style guided review replies with location, story angle, mood, audience hook, include/avoid notes, and caption choice.
- Added live-capable `discord dm-guided-review-send` and `discord dm-guided-review-poll` commands for private Discord DM guided review prompts/replies using environment-provided bot credentials.
- The guided review flow builds/reuses the local guided draft package service, persists accepted caption/hashtags/location/alt text/growth rationale when Andrew chooses a caption option, records a sanitized conversation context note, and updates the private DM conversation thread summary.
- DM-facing output distinguishes Meta-publishable v1 fields from review-only/local metadata, avoids local absolute paths, and confirms that no Meta publishing endpoints are called.
- A Discord-only live smoke test now makes sense after this PR is merged and a real draft is available: send a guided-review prompt, reply in the private DM with location/story/mood/hook/caption choice, then poll/apply it. Do not run live Instagram publish execution.
- Scheduling guidance and explicit draft/publish approval prompts move to `feat/discord-schedule-queue-guidance`.

**Verification for current branch slice:**

```bash
.venv/bin/python -m pytest tests/test_dm_guided_review.py -q
.venv/bin/python -m pytest -q
```

Current local result: `10 passed` focused; `139 passed` full suite.

**Expected behavior:**
- Guide Andrew through post type, hook-first caption direction, hashtags, location confirmation, and alt text/review-only metadata.
- Incorporate Andrew-provided context from the DM conversation.
- Provide concise recommendations with rationales rather than just open-ended questions.
- Support DM replies that persist accepted caption/content decisions to SQLite.
- Confirm when a requested field is local/review-only rather than publishable through Meta Graph.
- Do not run live Instagram publish execution in this milestone.

### Milestone 15: `feat/discord-schedule-queue-guidance`

**Latest live DM smoke observation:** Andrew confirmed user-initiated Discord DM draft creation, back-and-forth copy review, and contact-sheet image selection worked in the Discord app. The main discovered gap is candidate/media narrowing: a broad request such as "San Francisco spring flowers" can currently select an overly broad year/folder scope and generate an unusably large contact sheet with hundreds of images. Future selection work should improve semantic request-to-directory/media matching, cap initial contact-sheet size, and ask a narrowing question before rendering huge sheets.

**Goal:** Let the Discord DM bot guide Andrew from approved draft to scheduled queue while optimizing cadence toward follower growth.

**Delivered behavior:**
- Added `src/post_relay/dm_scheduling.py` for private-DM schedule guidance and final local publish-approval handling.
- Added live-capable `discord dm-schedule-send` and `discord dm-schedule-poll` commands for sending schedule options and applying Andrew's first private-DM reply.
- Added no-network `discord dm-schedule-apply` fallback for copied replies such as `slot 1` or explicit ISO timestamps.
- Added no-network `discord dm-publish-approval-apply` fallback for recording final local publish approval from an explicit `approve publish` DM reply inside the configured final-approval window.
- Schedule guidance uses simple interpretable Tue/Thu/Sun 09:30 slots, a 36-hour lead-time buffer, and skips already scheduled days so posts do not cluster or dump backlog at once.
- The DM flow reuses the existing local scheduling state machine: schedule choices require `approved_for_queue`, move drafts to `scheduled`, and final approval moves scheduled drafts through `awaiting_publish_approval` to `ready_to_publish` without Meta calls.

**Safety notes:**
- Discord credentials are read only from environment/private configuration in live send/poll commands.
- The no-network apply commands are available for copied DM replies and do not call Discord or Meta.
- Final publish approval recorded through DM still only prepares the local draft for guarded publish validation; it does not publish to Instagram.
- Live Instagram publish execution remains out of scope for Discord milestones.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_scheduling.py -q
.venv/bin/python -m pytest -q
```

Current local result: `9 passed` focused; `152 passed` full suite.

### Milestone 16: `feat/discord-dm-opportunity-model` (completed in PR #41)

**Goal:** After the user-initiated DM workflow is proven, add local models/services for agent-initiated post opportunities without sending Discord DMs yet.

**Delivered behavior:**
- Added a `post_opportunities` SQLite table for local agent-initiated suggestion records with trigger type/key, title, sanitized summary, rationale, suggested next action, status, optional candidate/draft links, snooze/dismiss metadata, and timestamps.
- Added `src/post_relay/post_opportunities.py` for local opportunity creation, active dedupe by trigger type/key, sanitization, listing, dismissing, snoozing, and candidate-linked conversion to a draft.
- Added `post-relay opportunities create|list|snooze|dismiss|convert-to-draft` CLI commands.
- Conversion to draft reuses the existing candidate-to-draft creation path so post type and idempotency stay consistent.
- Mutating CLI commands commit their local SQLite changes and explicitly confirm that no Discord or Meta network calls were made.
- Active duplicate opportunities are reused; terminal opportunities can be recreated later for the same trigger if needed.
- Tests cover local creation/dedupe/sanitization, validation, dismiss, snooze, candidate conversion, and CLI behavior.

**Safety notes:**
- No Discord DMs, Meta calls, or other network integrations are performed in this milestone.
- Secret-like values in opportunity summaries are redacted before persistence/output.
- This milestone only creates and manages local opportunity records; safe local trigger checks remain the next milestone.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_post_opportunities.py -q
.venv/bin/python -m pytest -q
```

Current local result: `5 passed` focused; `157 passed` full suite.

### Milestone 17: `feat/opportunity-trigger-checks` (completed in PR #42)

**Goal:** Add safe local checks that create agent-initiated post opportunities before any DM is sent.

**Delivered behavior:**
- Added `src/post_relay/opportunity_checks.py` for safe local trigger planning/execution.
- Added `post-relay opportunities check`, dry-run by default, with `--execute` required to persist local opportunity records.
- Detects undrafted indexed candidate groups as `new_media` opportunities, capped by `--max-new-media-candidates`.
- Detects cadence due from local scheduled/posted draft history with configurable `--cadence-due-after-days`.
- Detects local inactivity when no scheduled/posted history and no more specific new-media opportunity is available.
- Supports manually seeded local opportunities with `--manual-trigger-type`, `--manual-trigger-key`, title, summary, rationale, and suggested next action before external adapters exist.
- Skips existing active opportunities, future snoozes, dismissed opportunities, and already-converted opportunities for the same trigger key during automated checks.
- Prints explicit no-Discord/no-Meta messaging for both dry-run and execute paths.

**Safety notes:**
- Dry run is the default and writes no opportunity records.
- Execute mode only writes local SQLite opportunity records; it does not send Discord DMs, query external event/trend APIs, or call Meta publishing endpoints.
- Manual summary text still flows through the existing opportunity sanitizer before persistence/output.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_opportunity_trigger_checks.py -q
.venv/bin/python -m pytest -q
```

Current local result: `4 passed` focused; `161 passed` full suite.

### Milestone 18: `feat/live-carousel-publish-smoke-notes` (preflight completed in PR #43)

**Goal:** After Discord photo selection and guided post-package approval are proven, run one explicitly approved live carousel smoke test through the guarded carousel path, ideally using R2-staged public HTTPS image URLs, then document observed Meta behavior.

**Current branch progress:**
- Branch `feat/live-carousel-publish-smoke-notes` started from synced `main` after PR #42.
- Safe preflight notes were added at `docs/publishing/live-carousel-smoke-preflight-2026-05-17.md`.
- Current local smoke candidate is draft `2`, a 5-image Mt. Cook carousel with caption text present and R2 dry-run planning ready.
- Live execution is not yet run because draft `2` remains `drafting`, active draft/publish approvals still need to be completed intentionally, R2 upload execution has not been run, and Andrew has not explicitly authorized the live Meta `--execute` publish command in the active session.
- No Discord DMs, R2 upload execution, or Meta publishing endpoints were called during preflight.

**Verification:**

```bash
.venv/bin/python -m pytest -q
```

Current local result after PR #43 merge: `161 passed` full suite.

**Preconditions:**
- Discord selection has selected the final carousel media from a larger suggested set.
- Discord guided review has confirmed post type, content direction, caption, hashtags, location handling, alt text/review-only metadata, and schedule intent.
- Andrew has confirmed the selected media order and lead/cover in Discord.
- Keep the single-image live smoke result documented as the baseline.
- Preserve double approval before any live publish; refresh draft and publish approvals after any selection changes.
- Use POST for Meta media container creation and publish endpoints.
- Run R2 staging and `meta validate-carousel-publish --from-staged-r2 --dry-run` first and review the sanitized plans.
- Do not run `--execute` without Andrew's explicit approval in the active session.

**Expected behavior:**
- Confirm Meta accepts one child media container per carousel image with `is_carousel_item=true`.
- Confirm Meta accepts a carousel container with `media_type=CAROUSEL` and ordered child ids.
- Confirm container status polling and media publishing work for the linked `andrewhml` account.
- Record sanitized child container ids, carousel container id, status, and published media id.
- Move the draft to `posted` only after Meta returns a published media id.

### Milestone 19: `feat/dm-candidate-narrowing` (completed in PR #44)

**Goal:** Reduce the risk that a broad natural DM request selects a huge weak candidate folder and produces an unusable contact sheet.

**Delivered behavior in branch:**
- Added a `narrowing_question` result for DM intake when the best local candidate has zero keyword overlap and at least 120 photos.
- For those weak huge matches, `dm intake` now withholds candidate suggestions, sets `Next safe step: candidate narrowing`, and asks for a date, neighborhood, folder name, or 5-10 filenames before rendering a contact sheet.
- Matched large candidates are still suggested, but the DM text explicitly warns: `Large set: narrow before rendering a contact sheet.`
- Candidate ranking now includes `source_folder` text in addition to the public title/reason/post type, improving folder-name matching without adding external services.
- All behavior remains local-only: no Discord, R2, or Meta network calls.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_intake.py -q
.venv/bin/python -m pytest -q
```

Current local result: `10 passed` focused; `163 passed` full suite.

## Current project state

As of the first live carousel smoke, the local-first workflow is past the original scaffold phase:

- Local processed/NAS folders are still the source of truth; generated artifacts and R2 objects are disposable staging/review layers.
- Candidate groups, drafts, media selection, context questions, guided packages, scheduling, draft approval, and publish approval all exist as local SQLite/CLI workflows.
- Private Discord DM flows are live-capable for user-initiated intake, X-from-Y media selection, guided review/copy acceptance, scheduling, and double-confirmed final local publish approval.
- Agent-initiated suggestions are modeled locally through `post_opportunities` and safe trigger checks; proactive outreach now has local DM planning and mark-sent controls, but no live proactive Discord send should happen without explicit active-session authorization.
- DM intake now avoids the worst broad-request failure mode by asking for narrowing cues before suggesting huge weak matches, matched large sets point operators to bounded artifact planning, and natural request matching uses local folder/year/filename descriptors with explainable rationale.
- Oversized full contact-sheet renders are blocked by `drafts artifacts render`; instead, the CLI prints a bounded, DM-safe first-pass plan with narrowing/sample guidance and no source paths.
- Single-image publish validation has completed one live smoke test. The first live carousel smoke for draft `2` succeeded through the guarded Meta path. Schedule enforcement, final publish caption/metadata preview, publish exports, resolved Meta `location_id` support, local post-publish analytics snapshots, explicit read-only insights storage, local-only recommendation feedback summaries, post terminology cleanup, local follower-growth tracking, Meta token extension, DM next-action planning, durable scheduled publish approvals, and warm-dark chat artifact rendering are implemented on `main`.

## Immediate next plan

This handoff refresh follows the chat artifact refresh PR #62, contact-sheet design v2 hardening PR #64, and DM operating-loop hardening PR #65, all merged to `main`.

1. Use `analytics feedback-summary` plus `analytics follower-summary` as deterministic advisory baselines when planning the next reviewed post.
2. Andrew validated the refreshed Stage 1/Stage 2/Stage 3 assets in a real Discord chat against the upcoming post; continue the upcoming-post operation through the Discord agent rather than adding more artifact design work first.
3. Current engineering branch/PR: `feat/proactive-opportunity-dm-controls` / PR #66, focused on rendering safe proactive opportunity DM copy plus explicit local mark-sent controls without sending Discord, R2, or Meta requests.
4. After that, choose between `feat/video-reel-validation` or `feat/local-media-discovery-enrichment`.
5. Keep recommendation and follower-growth feedback advisory-only until several real posts and account snapshots provide enough signal.
6. Keep live-safe defaults: no Discord sends, no R2 `--execute`, and no Meta `--execute` unless explicitly authorized in the active session.

## Recent completed milestones and current roadmap

### Milestone 20: `feat/dm-bounded-review-artifacts` (completed in this branch)

**Goal:** Make broad DM-driven review safe and usable by preventing oversized contact sheets and offering a bounded first-pass review package.

**Delivered behavior in branch:**
- Added `BoundedReviewArtifactPlan` and `plan_bounded_review_artifacts_for_draft(...)` to classify draft media volume before artifact rendering.
- `drafts artifacts render` now blocks full contact-sheet rendering for drafts with at least 120 included photos and prints a bounded first-pass plan instead of creating thumbnails/contact sheets.
- The bounded plan includes media count/classification, a capped first-pass recommendation, `media-plan`/`media-edit` operator commands, and a DM-safe narrowing prompt.
- DM intake warnings for matched large candidates now point operators to the bounded artifact plan after candidate selection.
- Plan/render-block output avoids absolute source paths and filenames and makes clear no Discord, R2, or Meta network calls were made.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_intake.py tests/test_review_artifacts.py -q
.venv/bin/python -m pytest -q
```

Focused local result: `17 passed`.

### Milestone 21: `feat/dm-semantic-candidate-matching` (completed in this branch)

**Goal:** Improve natural DM request matching beyond substring overlap while staying local-first.

**Delivered behavior in branch:**
- DM candidate ranking now builds local searchable descriptors from candidate title/source folder, source year, reason/post-type metadata, and candidate filenames.
- Matching supports small local aliases for common location/description tokens such as `sf` → `san francisco`, `nyc` → `new york`, and `blossoms` → `flowers`.
- Strong folder/location and filename matches outrank generic year-only matches, so specific local sets are preferred over generic large processed folders.
- DM-facing output includes concise match rationale lines without leaking absolute source paths or filenames.
- Embeddings, image-content analysis, and external services remain out of scope.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_intake.py -q
.venv/bin/python -m pytest -q
```

Focused local result: `12 passed`.

### Milestone 22: `feat/dm-double-confirm-publish-approval` (completed in this branch)

**Goal:** Make Discord DM final publish approval a two-message confirmation flow backed by the existing active `publish` approval flag/table instead of treating approval as only a draft status.

**Delivered behavior in branch:**
- Publish approval guidance now states the double-confirm sequence: first `approve publish`, then `confirm publish approval for post #<id>`.
- The first DM reply records no approval flag and leaves the post scheduled while updating the conversation thread to wait for the second confirmation.
- The second confirmation records the active `publish` approval through the existing approvals table, moves the post through the guarded local publish-approval state machine to `ready_to_publish`, and keeps Meta publish execution separate.
- A final confirmation phrase without the pending first step is rejected in the Discord DM poll path, preventing a one-message bypass.
- Added live-capable `discord dm-publish-approval-send` and `discord dm-publish-approval-poll` commands plus no-network apply support for the same two-step local state transition.
- Updated README/AGENTS command references and the Post Relay content workflow skill so future agents preserve the two-step approval semantics.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_scheduling.py -q
.venv/bin/python -m pytest -q
```

Current local result: `14 passed` focused; `174 passed` full suite.

### Milestone 23: `feat/live-carousel-publish-smoke-execution`

**Goal:** Complete the guarded live carousel smoke only after the preflight blockers are resolved and Andrew explicitly authorizes the Meta `--execute` command in the active session.

**Observed live smoke result on 2026-05-18:**
- Draft `2` was packaged, content-approved, scheduled for `2026-05-19T10:00:00-04:00`, double-confirmed for final publish approval, R2 staged, dry-run reviewed, and explicitly authorized for Meta `--execute` in the active session.
- Read-only Meta validation succeeded for Page `Andrewhml` (`998312870038313`) and linked Instagram account `andrewhml` (`17841400498120050`), with media count `207` before the publish.
- The first execute attempt failed before publishing because the stored Meta token had expired; the draft moved to `failed`. After a fresh Facebook Graph user token was provided and read-only validation passed, the draft was restored through the allowed `failed -> ready_to_publish` transition and dry-run validation was repeated.
- The live carousel execute path succeeded for draft `2`: five child containers were created, the parent carousel container reached `FINISHED`, and Meta returned published media id `18103350268949956`. Local draft status moved to `posted`.
- The execute command published immediately when run; it did **not** wait for or enforce the stored `scheduled_for` time. This is now a required hardening follow-up before the next real post.
- Hashtags and location were stored in local draft metadata, but hashtags were not appended to the caption sent to Meta and location remains local/review-only in the current capability matrix. This is now a required final-publish-preview/metadata follow-up.
- Source portrait images used 2:3-ish dimensions (`4672x7008`, ratio `0.667`) rather than an Instagram-optimized 4:5 feed export (`1080x1350` or equivalent). This is now a required publish-export/aspect-ratio follow-up.

**Safety rule:** Treat the first live carousel smoke as successful but not production-complete. Do not publish another real post until the next post-publish hardening milestones below are implemented or explicitly bypassed by Andrew in the active session.

### Milestone 24: `feat/publish-schedule-enforcement` (current branch)

**Goal:** Prevent accidental immediate publishing before the approved scheduled time.

**Implemented:**
- `meta validate-image-publish --execute` and `meta validate-carousel-publish --execute` inspect `draft.scheduled_for` when present.
- If `now < scheduled_for`, execute mode refuses before creating a publish attempt, before changing draft status to `posting`, and before calling Meta.
- Both execute commands expose `--now` for deterministic checks/tests and `--publish-now` as the explicit early-publish override. Use `--publish-now` only with Andrew's explicit active-session authorization.
- Domain tests cover before-schedule refusal without network calls, invalid schedule timestamps, and explicit override execution. CLI tests cover early refusal copy and redaction.
- `meta publish-scheduled --from-staged-r2` adds a scheduled-runner preflight/execute wrapper for due posts. Default mode performs no network calls and creates no publish attempts.
- Scheduled-runner preflight re-checks `ready_to_publish`, timezone-aware `scheduled_for`, due time, active draft and publish approvals, complete uploaded staged R2 draft media, caption, post type, and sanitized Meta-bound media URLs.
- Scheduled-runner execute mode reuses the existing guarded single-image/carousel Meta execute path after preflight; it still requires due time, active approvals, complete staged media, private env credentials, and explicit `--execute`.

**Safety rule:** The runner default is preflight only. Do not run `meta publish-scheduled --execute` until the approved scheduled time and only with Andrew's active-session authorization.

**Historical next-session note:** After Milestone 24 merged, work moved to Milestone 25 `feat/final-publish-preview-metadata`. That milestone is now completed in PR #50; the active next milestone is Milestone 26 `feat/publish-export-profiles`.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_publish_validation.py tests/test_scheduled_publish_runner.py tests/test_cli.py -q
.venv/bin/python -m pytest -q
```

### Milestone 25: `feat/final-publish-preview-metadata` (completed in PR #50)

**Goal:** Show and publish exactly the final metadata that Instagram will receive, avoiding hidden differences between local review metadata and Meta payload fields.

**Delivered behavior in branch:**
- Added `meta final-publish-preview --from-staged-r2`, a no-network command that renders the exact Meta-bound caption string, selected staged public URLs in publish order, publishable fields, and local/review-only fields.
- Added a shared final-caption composer so dry-run/execute publish validation and final preview use the same caption string.
- Stored hashtags are deduped and appended to the Meta `caption` payload for v1 publishing when they are not already present in the caption text.
- Location text remains explicitly `local/review-only`; it is shown in the final preview and publish approval guidance but is not sent as a Meta location tag.
- Review-only alt text/rationale remains local and is not silently sent to Meta endpoints.
- Discord/private-DM final publish approval guidance now distinguishes exact Meta-bound caption, hashtags embedded in caption, location text, and review-only alt text/rationale.

**Safety rule:** Final preview performs no Discord sends, no R2 upload/cleanup, and no Meta publishing calls. It is a human inspection step before any later explicit scheduled `--execute` publish.

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Move next to Milestone 26 `feat/publish-export-profiles` to generate Instagram-optimized publish assets, especially 4:5 portrait carousel exports, before future real posts.
3. Keep live-safe defaults: no Discord sends, no R2 `--execute`, and no Meta `--execute` in tests or docs examples unless explicitly labeled as requiring Andrew's active-session authorization.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_final_publish_preview.py tests/test_publish_validation.py tests/test_dm_scheduling.py tests/test_cli.py -q
.venv/bin/python -m pytest -q
```

### Milestone 26: `feat/publish-export-profiles` (completed in PR #51)

**Goal:** Generate Instagram-optimized publish assets from immutable source media before R2 staging/Meta publish, especially for portrait carousel posts.

**Required behavior:**
- Add export profiles for feed publishing, starting with `feed_portrait_4x5` (`1080x1350` or a configurable higher-resolution 4:5 equivalent), `feed_square` (`1080x1080`), and a landscape-in-portrait-carousel treatment.
- Preserve source media immutability: write exported publish assets under a generated artifact/export root, never over source Lightroom/NAS files.
- For carousel posts, choose a consistent aspect ratio based on the lead image and warn when included media have mixed orientations/aspect ratios.
- For portrait images like the Mt. Cook set (`~2:3`, ratio `0.667`), create intentional 4:5 crops or fits instead of leaving crop decisions to Instagram.
- For landscape images inside a portrait carousel, support a deliberate treatment: smart crop, blurred/extended background, or clean mat/canvas. The selected treatment must be visible in the preview and approved before staging.
- Add a publish-preview contact sheet using the actual exported images and dimensions, not the original source files.
- R2 staging for publish should use exported publish assets when present; review artifacts/contact sheets remain separate from publish assets.
- Add tests for dimensions, aspect ratio decisions, source immutability, mixed-orientation warnings, R2 plan resolution using exported assets, and dry-run output.

**Delivered behavior in branch:**
- Added `drafts publish-exports render --profile feed_portrait_4x5`, which renders immutable-source local publish assets under the configured `publish_exports.root`.
- Added `feed_portrait_4x5` (`1080x1350`) and `feed_square` (`1080x1080`) profile definitions, with portrait center-crop behavior and a clean-mat treatment for landscape images inside portrait exports.
- Added mixed-orientation warnings so carousel export review explicitly flags landscape/portrait sets before staging.
- Added a publish preview contact sheet built from the exported publish files rather than source Lightroom/NAS media.
- Updated R2 staging planning/upload so publish media use exported assets when a matching export package is present; review artifacts stay separate and optional.
- Added tests covering 4:5 dimensions, treatment decisions, source immutability, mixed-orientation warnings, R2 exported asset resolution, and CLI dry-run output.

**Safety rule:** Publish exports perform no Discord sends, no R2 upload/cleanup, and no Meta publishing calls. Source processed media must remain immutable; exported publish files are generated under `publish_exports.root` only.

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Move next to Milestone 27 `feat/location-tag-validation` to validate and safely support true Instagram location tags before analytics feedback work.
3. Keep live-safe defaults: no Discord sends, no R2 `--execute`, and no Meta `--execute` unless explicitly authorized in the active session.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_publish_exports.py tests/test_review_artifacts.py tests/test_r2_staging.py tests/test_r2_staging_upload.py tests/test_publish_validation.py tests/test_scheduled_publish_runner.py tests/test_final_publish_preview.py tests/test_cli.py -q
.venv/bin/python -m pytest -q
```

### PR #53 / Milestone 27: `feat/location-tag-validation`

**Goal:** Support Instagram location as a true publish tag, not just local review text, only after official Meta Graph capability is validated for Andrew's Page-linked Creator account.

**Delivered behavior in branch:**
- Validated the official `graph.facebook.com` content publishing shape: feed image and carousel parent container creation accept `location_id=<LOCATION_PAGE_ID>`; the official lookup route is read-only `GET /pages/search?q=...&fields=id,name,location,link`.
- Added resolved draft location tags in SQLite, stored separately from freeform `drafts.location_text` so prose is never converted into an inferred tag id.
- Added `drafts location-candidates --draft-id ... [--query ...]` so the bot can ask for a more specific place when context is vague, or use read-only Page search to present ranked candidate tags without setting anything.
- Added `drafts location-tag-set --draft-id ... --page-id ... --name ...` to persist an explicitly selected Facebook Page id; setting/changing the tag invalidates active approvals and moves approved drafts back to `needs_edits`.
- Updated final publish preview to render `Location handling: resolved Meta location tag` plus the exact `location_id` payload when a resolved tag exists; otherwise freeform location text remains local/review-only.
- Updated single-image and carousel publish execution to include `location_id` only from a resolved stored tag. Carousel child containers do not receive location ids; only the image container or carousel parent container does.
- Updated the Instagram capability matrix from `needs_validation` to `publishable_when_resolved` while keeping arbitrary/freeform `location_tag` metadata out of generic publishable filtering.
- Added tests for official page-search request construction, location candidate clarification/ranking, approval invalidation, CLI persistence, final preview payload rendering, carousel publish params, and local-only freeform location behavior.

**Safety rule:** `location_text` is still local/review-only. Post Relay sends a Meta location tag only when a reviewed Facebook Page `location_id` is explicitly stored on the draft and approvals have been reacquired after that material edit. Do not infer or fabricate location ids from captions, folder names, or user prose.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_location_tags.py tests/test_instagram_capabilities.py tests/test_discord_selection_payload.py -q
.venv/bin/python -m pytest -q
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Move next to Milestone 28 `feat/post-publish-analytics-feedback` to capture published media outcomes and start improving recommendations from real results.
3. Keep live-safe defaults: no Discord sends, no R2 `--execute`, and no Meta `--execute` unless explicitly authorized in the active session.

### PR #54 / Milestone 28: `feat/post-publish-analytics-feedback`

**Goal:** After safer publishing is in place, capture performance feedback so recommendations and export choices improve over time.

**Delivered behavior in branch:**
- Added `published_post_snapshots`, a local audit table keyed by draft and publish attempt, recording published media id, post type, final Meta-bound caption, ordered media URLs, media dimensions, scheduled time, actual publish time, and resolved location tag fields.
- Successful guarded single-image/carousel publish execution now records a local post-publish snapshot after Meta returns a published media id and the draft moves to `posted`.
- Added `analytics snapshot --draft-id ...` to backfill/render the local snapshot from existing successful publish attempts without network calls.
- Added `analytics insights-plan --draft-id ...` to render the read-only Meta insights endpoint/metric plan for the published media id without network calls; actual insights fetch/storage remains a follow-up.
- Snapshot dimension capture uses local uploaded staged-media records and exported asset files when available; missing/unreadable files are recorded as unknown rather than blocking the audit snapshot.
- Added tests for snapshot persistence, publish-path auto-capture, read-only insights planning, CLI rendering, and no-extra-network behavior.

**Safety rule:** Analytics snapshot and insights-plan commands do not call Discord, R2, or Meta. Actual insights collection must remain read-only and separate from publishing, and must not imply permission to execute a live publish.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_analytics_feedback.py tests/test_publish_validation.py -q
.venv/bin/python -m pytest -q
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Move next to read-only insights fetch/storage for published media, using `instagram_manage_insights` only if available and keeping no-network planning as the default safe path.
3. Then add recommendation feedback summaries that compare outcomes against caption length/style, carousel count/order, timing, location tag, and export format.

### PR #55 / Milestone 29: `feat/read-only-insights-feedback`

**Goal:** Add actual read-only insights fetch/storage for published media after confirming the current token has the required supported insight permission/scope. Keep the no-network `analytics insights-plan` command as the safe default and add explicit `--execute` only for read-only collection.

**Delivered behavior in branch:**
- Added `media_insight_snapshots`, a local audit table keyed to the published post snapshot, published media id, collection timestamp, parsed metrics, and raw sanitized payload JSON.
- Added `MetaGraphClient.get_media_insights(...)`, which uses `GET /{ig-media-id}/insights?metric=...` and preserves read-only method semantics.
- Added `analytics insights-fetch --draft-id ...` with dry-run default that renders the same endpoint/metrics and makes no Meta calls.
- Added `analytics insights-fetch --execute` to load private Meta config, call only the read-only insights endpoint, parse returned metric values, store the result locally, and render a no-publish safety summary.
- Kept metrics separate from drafts/publish attempts so insight collection cannot mutate approval, scheduling, or publish state.
- Added tests for Graph request construction, metrics parsing/storage, dry-run no-network behavior, and execute-mode CLI collection through an injected client.

**Safety rule:** `analytics insights-fetch` defaults to no-network dry-run. `--execute` may call Meta only for read-only insights collection and never calls publishing endpoints, Discord, or R2. It must be used only when the active token has the appropriate insights permission.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_analytics_feedback.py -q
.venv/bin/python -m pytest -q
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Move next to recommendation feedback summaries from stored `published_post_snapshots` + `media_insight_snapshots`.
3. Summaries should compare outcomes against caption length/style, carousel count/order, timing, resolved location tag usage, and export format, without auto-changing approved drafts or publishing anything.

### PR #56 / Milestone 30: `feat/recommendation-feedback-summaries`

**Goal:** Turn local published payload snapshots and stored insight metrics into human-readable recommendation feedback for future post planning.

**Delivered behavior in branch:**
- Added `analytics feedback-summary`, a local-only advisory CLI that reads stored `published_post_snapshots` and latest `media_insight_snapshots` for all recent posts or a specific `--draft-id`.
- Summaries include payload features: post type, media count/order, caption character count, hashtag count in final caption, schedule-vs-actual timing delta, resolved location tag presence, and export/aspect-ratio class.
- Latest stored insight metrics are included when available; when absent, the command renders a payload-only fallback plus the safe `analytics insights-fetch` command to collect metrics later.
- Renderer copy explicitly avoids causal claims from tiny samples and separates "observed signals" from conservative "next-post suggestions".
- Repository helpers list published snapshots and select the latest insight snapshot per draft without adding any network calls.
- Added tests for single-draft summaries, missing-insights fallback, latest-metric selection, and CLI no-network/no-state-mutation behavior.

**Safety rule:** `analytics feedback-summary` is advisory only. It makes no Discord, R2, or Meta calls and must not mutate posts, approvals, schedules, publish attempts, snapshots, or insight records.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_analytics_feedback.py -q
.venv/bin/python -m pytest -q
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Use `analytics feedback-summary --draft-id ...` or `--limit ...` as the deterministic advisory baseline when planning the next post.
3. Choose the next milestone from follower-growth progress tracking, private-DM operating-loop improvements, proactive opportunity DM controls, video/reel validation, or deeper local media discovery/enrichment.

### PR #57 / Milestone 31: `feat/post-terminology-copy`

**Goal:** Make agent/user-facing output refer to each lifecycle artifact as a post instead of a draft; keep `drafting` as a lifecycle status and retain existing CLI/storage names for compatibility.

**Delivered behavior in branch:**
- Post review, media-plan, guided-review, Discord DM, scheduling, publish approval, R2 staging, publish preview, and analytics output now label the artifact as `Post ID` / `post #...` instead of `Draft ID` / `draft #...`.
- The existing `drafts` command namespace and `--draft-id` option remain supported, with help text clarifying they identify a post through the legacy option name.
- Content approval copy now describes approval of post content while the status can still be `drafting`; `draft` remains only in internal model/schema names and lifecycle state values where changing it would be a compatibility migration.
- README/AGENTS/current-roadmap handoff text now documents the terminology rule for future agents.

**Safety rule:** This is a copy/terminology milestone only. It must not change persistence schema, approval guards, scheduling behavior, R2 execution behavior, Discord send behavior, or Meta publishing behavior.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_cli.py tests/test_discord_dm.py tests/test_dm_scheduling.py tests/test_draft_review_package.py tests/test_discord_preview_payload.py -q
.venv/bin/python -m pytest -q
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Use `analytics feedback-summary --draft-id ...` or `--limit ...` as the deterministic advisory baseline when planning the next post.
3. Complete PR #58 / Milestone 32 `feat/follower-growth-tracking`, then use `analytics follower-summary` alongside per-post feedback before selecting the next operating-loop milestone.

### PR #58 / Milestone 32: `feat/follower-growth-tracking` (current branch)

**Goal:** Track Andrew's creator-account follower progress locally so post planning can compare per-post feedback with account-level growth toward 5,000 followers.

**Delivered behavior in branch:**
- Added `account_metric_snapshots`, a local audit table for read-only Instagram account metrics: account id, username, follower count, follows count, media count, raw payload, and collection timestamp.
- Added `MetaGraphClient.get_instagram_account_metrics(...)`, using read-only `GET /{ig-account-id}?fields=id,username,followers_count,follows_count,media_count`.
- Added `analytics follower-fetch`, which defaults to dry-run/no-network output and only calls Meta/stores a snapshot with explicit `--execute`.
- Added `analytics follower-summary`, which reads local snapshots only and reports current followers, delta from the previous snapshot, progress toward the default 5,000-follower goal, and conservative next-post guidance.
- Kept follower tracking separate from post lifecycle state, approvals, schedules, publish attempts, Discord, R2, and Meta publishing endpoints.
- Added tests for read-only plan rendering, Graph request construction, storage, summary delta/progress calculation, and CLI dry-run no-network/no-state-mutation behavior.

**Safety rule:** Follower tracking is advisory analytics only. `analytics follower-fetch` defaults to dry-run; `--execute` may call only the read-only account metrics endpoint and must not mutate posts, approvals, schedules, publish attempts, post snapshots, or insight records.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_analytics_feedback.py -q  # 17 passed
.venv/bin/python -m pytest -q  # 220 passed
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Use `analytics feedback-summary` plus `analytics follower-summary` as local advisory baselines when planning the next post.
3. Complete PR #59 / Milestone 33 `feat/meta-token-extend`, then resume private-DM operating-loop improvements.

### PR #59 / Milestone 33: `feat/meta-token-extend` (current branch)

**Goal:** Reduce daily Meta token refresh friction by adding a safe local command that exchanges a valid short-lived Facebook Graph user token for a long-lived token and can update the private `.env` file without printing secrets.

**Delivered behavior in branch:**
- Added `MetaGraphClient.exchange_long_lived_user_token(...)`, which calls only `GET /oauth/access_token` with `grant_type=fb_exchange_token` and never calls publishing endpoints.
- Added `TokenExtensionResult` rendering that redacts returned access tokens while showing token type, `expires_in`, and calculated `expires_at`.
- Added `POST_RELAY_META_APP_ID` and `POST_RELAY_META_APP_SECRET` loading to Meta Graph config, with safe summaries that do not expose secret values.
- Added `update_meta_graph_access_token_env_file(...)` to replace only `POST_RELAY_USER_ACCESS_TOKEN` in the private env file through a temporary-file replace.
- Added `meta token-extend`, which defaults to dry-run/no-network output; `--execute` performs the exchange and `--update-env` explicitly updates `.env` with the extended token.
- Added tests for exchange request construction, missing app credentials, secret redaction, env-file replacement, CLI dry-run, and CLI update behavior.

**Safety rule:** Token extension is credential maintenance only. The command must redact old and new tokens plus app secrets, default to no network, and never call Meta publishing endpoints, Discord, R2, or mutate post lifecycle/analytics state. `.env` updates require explicit `--update-env`.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_meta_graph.py -q
.venv/bin/python -m pytest -q
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Use `meta token-extend --env-file .env` to inspect the dry-run plan; use `--execute --update-env` only after a valid short-lived token is in the private `.env`.
3. Complete PR #60 / Milestone 34 `feat/dm-next-action-planner`, then choose proactive opportunity DM controls, video/reel validation, or deeper local media discovery/enrichment.

### PR #61 / Milestone 35: `feat/durable-scheduled-publish-approval` (current branch)

**Goal:** Let Andrew give final publish approval once, schedule arbitrarily far in the future, and have the due scheduled-publish runner proceed from durable stored approval without a second manual approval inside Meta's 24-hour container window. Also make the agent aware of all locally scheduled posts before it recommends or schedules another slot.

**Delivered behavior in branch:**
- Added scheduled-post feedback rendering for all local posts with `scheduled_for` in scheduled/publish-approval/ready/posting states, sorted by scheduled time.
- `dm next-action` now includes the scheduled-post queue whenever any scheduled posts exist, so the agent can mention existing slots before suggesting another post time.
- Ready-to-publish `dm next-action` copy now treats active final publish approval as durable until a material edit invalidates it, and explains that Meta containers are created only when the due runner executes.
- `drafts schedule` echoes the scheduled-post queue after scheduling, so immediate CLI output warns when another post is already scheduled.
- Added regression coverage proving scheduled-publish preflight accepts active final approval older than 24 hours.

**Safety rule:** Stored final approval authorizes the scheduled runner only for the approved post, after its local `scheduled_for` time is due, while active content and publish approvals still exist and staged media/caption preflight passes. Material edits still invalidate approvals and require reapproval. Planner and schedule feedback remain local-only and do not call Discord, R2, or Meta.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_scheduling.py tests/test_dm_operating_loop.py tests/test_scheduled_publish_runner.py -q
.venv/bin/python -m pytest -q
```

### PR #60 / Milestone 34: `feat/dm-next-action-planner` (merged)

**Goal:** Make the private-DM operating loop less manual by adding a local planner that inspects the active thread/post status and tells the agent the next safe step without sending Discord, R2, or Meta requests.

**Delivered behavior in branch:**
- Added `dm next-action`, which can plan from `--draft-id`, an active `--discord-channel-id`, or the latest local post when no explicit target is provided.
- Added status-aware routing for candidate selection, media selection, content review, schedule prompting, double-confirmed publish approval prompting, guarded publish preflight, and post-publish analytics feedback.
- Suggested commands point to the existing gated Discord DM and local Meta/analytics commands while preserving separate content approval, scheduling, final publish approval, and live execution gates.
- Planner output is source-path-safe and always states that no Discord, Meta, or R2 network calls were made.
- Added focused tests for open intake threads, drafting posts, queue-approved posts, scheduled posts, ready-to-publish posts, and CLI rendering.

**Safety rule:** This planner is advisory/local-only. It must not send Discord messages, mutate post state, call R2, call Meta, or grant publish authorization. Live Meta `--execute` remains outside the planner and requires explicit active-session approval.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_operating_loop.py -q
.venv/bin/python -m pytest -q
```

**Next-session start here:**
1. First verify the current baseline: `.venv/bin/python -m pytest -q` should report the full suite passing.
2. Use `dm next-action --draft-id <id>` or `--discord-channel-id <dm-channel>` before choosing/sending the next private-DM prompt.
3. After this lands, choose proactive opportunity DM controls, video/reel validation, or deeper local media discovery/enrichment.

### PR #62 / Milestone 36: `feat/chat-design-refresh` (merged)

**Goal:** Integrate the new `assets/contact sheet/` contact-sheet and carousel-preview designs into Post Relay's local artifacts and chat/Discord preview surfaces.

**Reference plan:** `docs/plans/contact-sheet-chat-design-refresh.md`

**Design source files:**
- `assets/contact sheet/INTEGRATION_PROMPT.md`
- `assets/contact sheet/README.md`
- `assets/contact sheet/contact-sheet.jsx`
- `assets/contact sheet/carousel-preview.jsx`
- `assets/contact sheet/crop-helpers.js`
- `assets/contact sheet/contact-sheet-final.css`

**Delivered behavior:**
- The deterministic crop-helper contract (`fitCrop`, `cropBox`, `chessFromAnchor`, `chessSpan`, `ratioLabel`, `tightnessLabel`) is ported into tested Python helpers.
- The simple white contact sheet is replaced with a warm-dark/amber numbered contact sheet artifact that includes the A1-E5 crop grid vocabulary, visible number chips, filenames/meta below images, and lead/cover markers.
- Local final post preview artifacts show selected media in confirmed order, one locked Instagram aspect ratio, a lead marker, pagination dots, and caption preview.
- Dry-run Discord/chat payload copy references designed artifacts and the crop-feedback fallback before changing live-send behavior.
- Large-set guardrails, source media immutability, and local/no-network defaults are preserved.

**Safety rule:** Treat the React/CSS assets as the visual contract, but Post Relay's current CLI/Discord chat path should render static local artifacts with Pillow first. Rendering and dry-run preview commands must not send Discord messages, upload to R2, call Meta, mutate approvals/schedules, or modify local/NAS source media.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_contact_sheet_design.py tests/test_review_artifacts.py tests/test_final_post_artifacts.py tests/test_discord_selection_payload.py tests/test_dm_operating_loop.py -q
.venv/bin/python -m pytest -q
```

Current merged-main result: `248 passed` full suite.

### PR #64 / Milestone 37: `feat/contact-sheet-design-v2` (implemented in branch)

**Goal:** Refine the uploaded contact-sheet/final-approval design integration after direct visual feedback, then provide a local browser preview for review.

**Delivered behavior in branch:**
- Stage 1 now renders `contact-sheet-select.png` as a selection-only artifact: letter stickers and filenames only, with no crop frame, no A1-E5 grid, and no lead marker so the UI cannot imply crop decisions are already in play.
- Stage 2 renders `contact-sheet-crop.png` for selected media only, with crop framing, A1-E5 grid vocabulary, crop metadata, and lead marker.
- Stage 3 renders `final-post-preview.png` for approval, with ordered selected media, caption preview, and centered metadata tags.
- Review/final artifacts now render as high-DPI PNGs at 1440px wide with 192 DPI metadata to reduce text grain in Discord/browser previews.
- Tag/chip text centering accounts for font bounding boxes, fixing the prior top-heavy vertical padding.
- README, AGENTS, historical plan references, R2 staging expectations, and tests were cleaned up to use the new `contact-sheet-select.png`, `contact-sheet-crop.png`, and `final-post-preview.png` artifact names.
- `scripts/render_design_v2_example.py` generates a local three-stage browser preview at `data/review_artifacts/design-v2-example/index.html`.
- Andrew tested the refreshed assets in Discord chat with the upcoming post and confirmed they look great.

**Safety rule:** Artifact rendering remains local/static. It must not send Discord messages, upload to R2, call Meta, mutate approvals/schedules, or modify local/NAS source media.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_review_artifacts.py tests/test_final_post_artifacts.py tests/test_cli.py tests/test_r2_staging.py tests/test_r2_staging_upload.py tests/test_discord_selection_payload.py tests/test_publish_validation.py -q
.venv/bin/python -m pytest -q
```

Current branch result: `59 passed` focused; `248 passed` full suite.

**Next-session start here:**
1. PR #64 is merged and `main` is synced; `.venv/bin/python -m pytest -q` reports `248 passed`.
2. Andrew will continue the upcoming-post operation in Discord; engineering should not run live R2 or Meta commands for that post unless explicitly authorized in the active session.
3. Current branch/PR `feat/dm-operating-loop-hardening` / PR #65 should make the private-DM user-initiated loop first-class around the Stage 1/2/3 artifacts and no-network advisory commands.
4. Keep `feat/proactive-opportunity-dm-controls`, `feat/video-reel-validation`, and `feat/local-media-discovery-enrichment` as the following milestone candidates.

### PR #65 / Milestone 38: `feat/dm-operating-loop-hardening` (merged)

**Goal:** Make `dm next-action` safer and more useful as the operator entry point for the private-DM Stage 1/2/3 review loop.

**Delivered behavior in branch so far:**
- Drafting/needs-edits next-action output now leads with local artifact rendering before the live-capable DM selection send command, so `contact-sheet-select.png`, `contact-sheet-crop.png`, and `final-post-preview.png` stay visible in the operator path.
- Ready-to-publish next-action output now suggests no-network final preview and scheduled publish preflight commands without `--execute`; live Meta execution remains a separate active-session authorization step.

**Safety rule:** `dm next-action` remains advisory/local-only. It must not send Discord messages, mutate post state, call R2, call Meta, or imply live publish authorization. Any Meta `--execute` command must be typed intentionally only after Andrew explicitly authorizes it in the active session.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_operating_loop.py -q
.venv/bin/python -m pytest -q
```

### PR #66 / Milestone 39: `feat/proactive-opportunity-dm-controls` (landed)

**Goal:** Let the operator safely turn local post opportunities into proactive private-DM suggestions without implementing autonomous Discord outreach.

**Delivered behavior:**
- Added local `opportunities dm-plan --opportunity-id ...` output that renders sanitized suggested DM copy, candidate/post linkage, yes/snooze/dismiss reply controls, and exact operator follow-up commands.
- Added local `opportunities mark-dm-sent --opportunity-id ...` to record that an explicitly authorized proactive send happened outside the no-network planner path; active `dm_sent` opportunities continue to dedupe future trigger checks.
- `dm-plan` and `mark-dm-sent` make no Discord, R2, or Meta calls and do not convert opportunities or create posts automatically.
- Terminal opportunities such as dismissed/converted records cannot be marked as DM sent.

**Safety rule:** Proactive opportunity controls are local/operator-facing only. Do not send a proactive Discord DM unless Andrew explicitly authorizes the live send in the active session; after any authorized send, record only the local `dm_sent` status with `opportunities mark-dm-sent`.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_post_opportunities.py tests/test_opportunity_trigger_checks.py -q
.venv/bin/python -m pytest -q
```

### PR #67 / Milestone 40: `feat/local-media-discovery-enrichment` (open)

**Goal:** Add a no-network local metadata enrichment baseline to processed-folder discovery before generated tags, embeddings, or Immich/NAS enrichment.

**Delivered behavior in branch so far:**
- `index scan` reads supported local image files with Pillow and enriches scanned records with width, height, derived orientation/aspect ratio, and available EXIF date/camera/lens fields.
- The persisted `photos` records now store enriched date/camera/lens/dimension fields during indexing; lightweight migrations ensure older local databases have those columns before upsert.
- Unreadable or placeholder image files remain indexed with empty metadata, so fixture scans and partial/corrupt local libraries do not fail the discovery pass.
- CLI output reports how many photos received local metadata and explicitly states that no network calls were made.

**Safety rule:** This milestone is local-only. It must not call Immich, NAS APIs, Discord, R2, Meta, generated-tag models, or embedding services; source media remains immutable.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_config_and_scanner.py tests/test_media_enrichment.py tests/test_cli.py::test_cli_index_scan_and_library_stats -q
.venv/bin/python -m pytest -q
```

## Later milestones

- Video/reel validation after feed/carousel path is reliable.
- Generated local tags or perceptual/semantic narrowing on top of the completed no-network dimensions/EXIF enrichment, if kept auditable and local-first.
- Recommendation improvements using approval, revision, and engagement history after the first deterministic feedback summaries land.
- Candidate/media narrowing follow-ups for natural DM requests should now build on the completed local descriptor/alias ranking, bounded artifact guardrails, and local metadata enrichment: lightweight metadata search, generated tags, or Immich enrichment only if they stay auditable and local-first.
- Immich/NAS enrichment once the processed-folder MVP works.

## Known open questions

- Whether and when to add a live proactive Discord send command on top of the local `opportunities dm-plan`/`mark-dm-sent` controls.
- How far candidate/media narrowing should go after no-network dimensions/EXIF enrichment: generated tags, perceptual/semantic embeddings, or Immich metadata once reliable.
- Exact current Meta permission/token state before the next live publish or read-only insights collection run.
- Whether reel/video validation should happen immediately after publish hardening or wait until feed/carousel cadence and analytics are stable.

## Documentation maintenance rule

When a milestone is completed, update this file in the same PR or the immediately following docs PR:

- Move the milestone from "Next planned milestones" to "Completed milestones".
- Add important behavior and safety decisions discovered.
- Update the expected full-suite test count if it changes.
- Confirm the next planned milestone branch name.
