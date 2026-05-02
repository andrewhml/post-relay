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

### Current milestone: Draft records from candidates

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

## Current local verification command

Run this before opening or merging any PR:

```bash
.venv/bin/python -m pytest -q
```

Expected current result after draft-record milestone:

```text
20 passed
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

### Milestone 1: `feat/draft-review-package`

**Goal:** Produce a structured review package for each draft before Discord integration.

**Behavior:**
- Add a local command such as:

  ```bash
  .venv/bin/post-relay drafts preview --draft-id 1 --db data/post_relay.sqlite
  ```

- Output should include:
  - draft id
  - status
  - candidate title
  - post type
  - photo file paths in order
  - caption/location/hashtags placeholders
  - unresolved context notes
  - allowed next actions

**Reason:** This creates a stable, testable preview format before wiring Discord image/message delivery.

### Milestone 2: `feat/context-placeholders-and-questions`

**Goal:** Add missing-context detection and focused interview question records.

**Behavior:**
- Detect useful missing fields such as place, trip name, date, mood/story angle.
- Store unresolved questions against a draft or candidate group.
- Keep questions lightweight and factual first.

### Milestone 4: `feat/draft-approval-cli`

**Goal:** Implement explicit draft approval and edit invalidation locally before Discord.

**Behavior:**
- Add CLI commands for approving draft content direction.
- Persist approval records with type `draft`.
- Move status from `awaiting_review` to `approved_for_queue` only through allowed state transitions.
- Editing draft content after approval moves status to `needs_edits` and invalidates old approval for queue/publish purposes.

### Milestone 5: `feat/schedule-and-publish-approval-cli`

**Goal:** Add queue/scheduling and publish-approval workflow without live API calls.

**Behavior:**
- Set scheduled time/window.
- Request/record `publish` approval separately from draft approval.
- Move through `scheduled` -> `awaiting_publish_approval` -> `ready_to_publish`.
- Do not publish; this milestone only prepares state and audit trail.

### Milestone 6: `feat/meta-graph-client-readonly`

**Goal:** Build a sanitized Meta Graph client for read-only validation.

**Behavior:**
- Load tokens from environment or private `.env`, never committed.
- Use `graph.facebook.com` by default.
- Redact tokens from logs/errors.
- Read Page/IG account information only.
- No publishing endpoints yet.

### Milestone 7: `feat/controlled-image-publish-validation`

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
