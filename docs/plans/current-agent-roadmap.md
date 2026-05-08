# Current Agent Roadmap Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task when a milestone is large enough to delegate. Use one rollback-safe branch and PR per milestone.

**Goal:** Make the Post Relay plan discoverable and executable for future agents across sessions.

**Architecture:** Post Relay is a local-first Python CLI and SQLite workflow. The repo currently supports source config loading, media indexing, library stats, candidate group building/listing, and guarded draft workflow states. The next milestones should turn indexed candidate groups into drafts, then add review, scheduling, approval, and eventually official Meta Graph publishing.

**Tech Stack:** Python 3.9+, SQLite, Typer, Pydantic, PyYAML, Pillow, pytest, GitHub PR milestone workflow.

---

## Source of truth docs

Future agents should read these files before implementing:

1. `AGENTS.md`
2. `README.md`
3. `docs/plans/current-agent-roadmap.md`
4. `implementation-plan.md`
5. `technical-design.md`
6. `requirements.md`
7. `setup-checklist.md`

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

Expected current result after guided draft package milestone:

```text
107 passed
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

## Next planned milestones

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

### Milestone 9: `feat/discord-guided-draft-package` (completed in PR TBD)

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

### Milestone 10: `feat/instagram-capability-matrix`

**Goal:** Make Post Relay explicit about which Instagram post fields it can publish programmatically and which remain local/review-only.

**Expected behavior:**
- Document and test capability handling for media URLs/carousel children, caption text, hashtags in captions, local alt text, location tagging, collaborators, music, product tags, story/reel-only fields, and future unsupported fields.
- Prevent unsupported metadata from silently being sent to Meta publish endpoints.
- Show review-only metadata clearly in Discord so Andrew can still use it manually when useful.
- Keep publish attempts sanitized.

### Milestone 11: `feat/discord-selection-bot`

**Goal:** Let Andrew interact with the Discord bot to choose X photos from Y suggestions and persist the choice into the draft media selection.

**Expected behavior:**
- Send a selection message to the configured Discord review channel.
- Accept exactly X selected photo numbers plus a lead/cover choice through Discord interactions or a command fallback.
- Apply the selection through the same local service as the CLI harness.
- Confirm selected count, lead/cover, final included order, excluded photos, and any approval invalidation back to Discord.
- Reject incomplete, duplicate, out-of-range, or too-large selections with actionable feedback.
- Keep Discord credentials private; no tokens or secrets in git, logs, or chat.
- Do not call Meta publishing endpoints in this milestone.

### Milestone 12: `feat/discord-guided-review-bot`

**Goal:** Expand the live Discord bot from media selection into a guided post-building conversation for post type, content, metadata, and schedule alignment.

**Expected behavior:**
- Guide Andrew through post type, media choice, caption direction, hashtags, location confirmation, alt text/review-only metadata, and schedule slot.
- Provide concise recommendations with rationales rather than just open-ended questions.
- Support natural-language revisions and persist accepted decisions to SQLite.
- Require explicit draft approval before queueing and explicit publish approval before live publish.
- Confirm when a requested field is local/review-only rather than publishable through Meta Graph.

### Milestone 13: `feat/discord-schedule-queue-guidance`

**Goal:** Let the Discord bot guide Andrew from approved draft to scheduled queue while optimizing cadence toward follower growth.

**Expected behavior:**
- Recommend schedule slots using configured cadence and simple interpretable rules.
- Avoid clustering similar posts or dumping too much backlog at once.
- Ask Andrew to approve or adjust the proposed slot in Discord.
- Persist the chosen schedule with the existing scheduling state machine.
- Request final publish approval near the publish window according to the configured policy.

### Milestone 14: `feat/live-carousel-publish-smoke-notes`

**Goal:** After Discord photo selection and guided post-package approval are proven, run one explicitly approved live carousel smoke test through the guarded carousel path, ideally using R2-staged public HTTPS image URLs, then document observed Meta behavior.

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

## Later milestones

- Video/reel validation after feed/carousel path is reliable.
- Analytics/insights collection and follower-growth progress tracking.
- Recommendation improvements using approval and engagement history.
- Immich/NAS enrichment once the processed-folder MVP works.

## Known open questions

- Exact processed photo source path(s) on Andrew's machine/NAS mount.
- Whether to create local preview thumbnails or lightweight contact sheets before Discord integration.
- How Hermes/Discord should handle image preview delivery reliably, given prior messaging-gateway image issues.
- Exact current Meta permission/token state at the time publishing validation starts.
- Whether the first draft generator should be rule-based placeholders or LLM-assisted captions.

## Documentation maintenance rule

When a milestone is completed, update this file in the same PR or the immediately following docs PR:

- Move the milestone from "Next planned milestones" to "Completed milestones".
- Add important behavior and safety decisions discovered.
- Update the expected full-suite test count if it changes.
- Confirm the next planned milestone branch name.
