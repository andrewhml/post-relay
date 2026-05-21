# Recommendation Engine Roadmap

## Status

Current planning document. Created after PR #84 (`feat/r2-setup-doctor`) when Andrew paused the managed R2 staging direction and asked to look for higher-leverage opportunities that make the agent smarter and start a true recommendation engine.

This roadmap is intentionally local-first and advisory. It should improve Post Relay's judgment without adding setup burden, hidden automation, or new live side effects.

## Product goal

Post Relay should become better at answering:

1. What should we post next?
2. Why is this set promising?
3. What format, hook, caption direction, and schedule are likely best?
4. What information is missing, and what can the agent infer safely from local context?
5. What has Andrew approved, revised, published, or learned before that should influence this recommendation?

## Available local signals

Start with signals already in the local database or deterministic local files:

- Active user/agent goal artifact: north-star statement, audience, content pillars, cadence, success metrics, strategy notes, constraints, and version history.
- Candidate group features: source folder, year, file count, media type mix, filename descriptors, local aliases, and candidate post type.
- Media features: dimensions, orientation, aspect ratio, EXIF date/camera/lens fields when available, crop feedback, inclusion/order/lead state, export readiness, missing-file status.
- Draft/post lifecycle: status, selected post type, caption, hashtags, location text, resolved location tag if any, schedule, content approval, publish approval, material-edit invalidations.
- Review artifacts: whether selection/crop/final preview artifacts exist and whether a post is blocked on a review gate.
- Guided package history: accepted location/story/mood/hook/caption/hashtag/local alt-text fields.
- DM and opportunity history: local intake messages, next-action output, opportunity trigger type/key/status, snooze/dismiss/convert outcomes.
- Published payload snapshots: post type, caption traits, hashtag count, location tag presence, media count, staged/export dimensions, publish time.
- Stored read-only insights: latest locally stored metrics from explicit `analytics insights-fetch --execute` or `analytics collect-due --execute` runs.
- Stored account/follower snapshots: follower/follows/media count trends from explicit account-metric collection.
- Approval/revision patterns: how often Andrew edits captions, changes selection, changes crop, rejects opportunities, or approves specific content directions.

Do not require live network calls to produce a recommendation. Recommendation commands should consume stored local state by default.

## Recommendation surfaces

Potential CLI surfaces, to be chosen milestone-by-milestone:

```bash
.venv/bin/post-relay goals show --db data/post_relay.sqlite
.venv/bin/post-relay goals agent-brief --db data/post_relay.sqlite
.venv/bin/post-relay recommendations signals --db data/post_relay.sqlite
.venv/bin/post-relay recommendations candidates --limit 10 --db data/post_relay.sqlite
.venv/bin/post-relay recommendations for-post --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay recommendations schedule --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay recommendations questions --post-id 1 --db data/post_relay.sqlite
```

Early outputs should be plain text or JSON-friendly tables with:

- rank or priority
- recommendation label
- rationale bullets
- supporting signals
- missing information
- next safe command
- explicit no-side-effect statement

## Suggested milestone sequence

### Milestone A: `docs/recommendation-engine-roadmap`

Define the recommendation problem, input signals, safety boundaries, and first implementation slices. No runtime behavior changes.

Verification:

```bash
.venv/bin/python -m pytest -q
```

### Milestone B: `feat/user-goal-artifact` (PR #86)

Add a durable local goal artifact that the user and agent can agree on before deeper recommendation work.

Implemented behavior:

- Store one active user/agent goal with title, goal statement, target audience, content pillars, desired cadence, success metrics, strategy notes, constraints, reviewer, and timestamps.
- Store immutable goal versions on each create/update so recommendation behavior can cite the current agreed north star and preserve an audit trail.
- Add local-only CLI commands:
  - `goals init`
  - `goals show`
  - `goals agent-brief`
- Render a compact agent brief that future recommendation commands can read before suggesting content, asking questions, or proposing proactive opportunities.
- Make no network calls and mutate no posts, approvals, schedules, opportunities, Discord, R2, Meta, or publish state.

Verification:

```bash
.venv/bin/python -m pytest tests/test_user_goals.py -q
.venv/bin/python -m pytest -q
```

### Milestone C: `feat/chat-goal-onboarding` (PR #87)

Make first-run chat guidance prompt for the active goal before the agent recommends a first post.

Initial behavior:

- Extend `setup` output with a `goals init` next command so local setup and goal setup happen together.
- Make `dm next-action` return a local `goal_onboarding` plan when no post/thread is active and no active goal exists.
- The prompt should ask for goal statement, target audience, content pillars, desired cadence, success metrics, strategy notes, and constraints.
- Preserve existing post/thread flows once an active goal exists or an active DM thread/post is already in progress.
- Make no network calls and mutate no posts, approvals, schedules, opportunities, Discord, R2, Meta, or publish state.

Verification:

```bash
.venv/bin/python -m pytest tests/test_dm_operating_loop.py tests/test_setup_wizard.py -q
.venv/bin/python -m pytest -q
```

### Milestone D: `feat/recommendation-signal-baseline`

Add a no-network command that summarizes available recommendation signals and data coverage. It should answer which local signals exist, which are missing, and which are too sparse to trust.

Initial behavior:

- Count candidate groups, posts by lifecycle state, selected media, accepted guided packages, published snapshots, insight snapshots, follower snapshots, approvals, revisions/invalidations, scheduled posts, opportunities, and DM intake rows where available.
- Report sparse-signal warnings, e.g. not enough published posts or insight snapshots to weight performance strongly.
- Print next safe commands for collecting or reviewing missing local signals.
- Make no network calls and mutate no state.

### Milestone E: `feat/candidate-ranking-signals`

Rank candidate groups with deterministic, explainable local scoring.

Initial scoring dimensions:

- readiness: source files exist, dimensions known, export compatibility, not too large for review without narrowing
- content potential: reasonable carousel size, coherent folder/year descriptors, strong filename/location hints
- diversity: avoid repeating the same trip/location/topic too soon when local history exists
- learning signal: prefer sets related to prior approvals or published posts that performed well, only when stored data is sufficient
- effort: lower friction for posts with existing accepted context, selected media, or review artifacts

The command should explain every score contribution and avoid pretending sparse analytics are conclusive.

### Milestone F: `feat/smarter-context-questions`

Reduce unnecessary interview questions by using local context first.

Behavior ideas:

- Suppress questions already answered by accepted guided package fields, explicit draft content, or local folder descriptors.
- Mark inferred facts as assumptions unless they are confirmed by stored user input.
- Ask targeted follow-up questions only for publish-relevant uncertainty: exact location tag, story angle, people/collaborators, date-sensitive context, or accessibility details.
- Keep freeform `location_text` local/review-only and never treat it as a Meta location tag.

### Milestone G: `feat/schedule-recommendations`

Suggest schedule windows from stored local account/post signals and priors.

Behavior ideas:

- Read local scheduled queue first.
- Use account timezone/config and stored follower summaries where available.
- Prefer conservative priors while account data is sparse.
- Explain why a slot is suggested and list conflicts.
- Do not schedule automatically.

### Milestone H: `feat/caption-style-recommendations`

Use approval/revision/published feedback to advise caption direction.

Behavior ideas:

- Track hook style, length, pun/wit level, itinerary/saveability, location specificity, and hashtag count from accepted/published posts.
- Compare draft captions to historically approved traits.
- Suggest edits as advisory text only; do not overwrite copy unless a separate explicit edit command is run.

## Safety rules

- Recommendation commands are local-first, no-network, and advisory by default.
- They must not send Discord messages, upload to R2, delete R2 objects, call Meta publish routes, approve content, approve publishing, schedule posts, mutate draft lifecycle state, or create publish attempts.
- Read-only insight/account collection remains a separate explicit analytics command with `--execute`; recommendation commands consume stored snapshots.
- Do not fabricate facts from filenames, folder names, or model guesses. Label assumptions and ask for confirmation when facts matter.
- Keep freeform `location_text` local/review-only. Only a separately stored reviewed Facebook Page `location_id` is publishable.
- Do not optimize for engagement at the expense of Andrew's taste, source-media truth, or review safety.

## Open questions

- Which local tables contain enough revision/approval history today to support useful scoring without schema changes?
- Should recommendation output be stored for audit, or recomputed on demand until the scoring model stabilizes?
- How should Andrew's qualitative taste feedback be captured without creating a heavy labeling workflow?
- When should generated tags, embeddings, or Immich/NAS enrichment become worth the added complexity?
