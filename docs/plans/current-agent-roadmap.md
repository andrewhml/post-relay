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

### Current milestone: Meta Graph client readonly

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
- No publishing endpoints or media container endpoints are implemented in this milestone.

## Current local verification command

Run this before opening or merging any PR:

```bash
.venv/bin/python -m pytest -q
```

Expected current result after meta-graph-client-readonly milestone:

```text
53 passed
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

### Milestone 1: `feat/controlled-image-publish-validation`

**Goal:** Validate one controlled single-image publish using the official Meta route.

**Preconditions:**
- Andrew explicitly provides/sets local token environment variables.
- Draft and publish approval flows exist and are tested.
- A safe test image/caption is chosen.

**Behavior:**
- Create publish container.
- Poll status.
- Publish only after explicit publish approval.
- Store remote ids and sanitized logs.
- Document any account/app limitations discovered.

## Later milestones

- Carousel publish support after single-image publish is validated.
- Video/reel validation after feed/carousel path is reliable.
- Discord presenter and approval capture.
- Analytics/insights collection.
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
