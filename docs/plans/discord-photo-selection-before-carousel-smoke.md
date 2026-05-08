# Discord Photo Selection Before Carousel Smoke Test Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Use one rollback-safe branch and PR per milestone.

**Goal:** Let Andrew interact with the Discord bot to choose X photos from Y suggested candidate photos, align on post type/content/metadata/schedule, and approve the complete post package before running any live carousel smoke test on Instagram.

**Architecture:** Keep Post Relay local-first, growth-oriented, and approval-gated. Build deterministic local services first, then expose them through a Discord conversation layer that presents numbered suggested photos, explains format recommendations, asks focused context questions, drafts attention-grabbing content, records Andrew's explicit decisions, and schedules approved posts. Only after Discord-guided selection, draft approval, publish approval, staged-R2 dry-run, and explicit active-session authorization should a live publish be attempted.

**Tech Stack:** Python 3.9+, SQLite, Typer, pytest, existing draft media-selection service, existing Discord preview payload harness, Discord bot/interactions, local review artifacts, optional R2 staging for public HTTPS media.

---

## Product decision

The live carousel smoke test should no longer be the next milestone. Before posting anything live, Post Relay should support a Discord review interaction where Andrew can select a target count of photos from a larger suggested set, for example "pick 5 from these 12 suggestions." The selected photos become the draft's included media in the chosen order, with an explicit lead/cover, and any existing approvals are invalidated as a material edit.

The primary live Discord surface should be Andrew's private DM with the agent, not a public or semi-public review channel. A post conversation can be initiated either by Andrew, who may DM the agent with context at any time, or by the agent when a local opportunity trigger says it is useful to collaborate on a post. Agent-initiated examples include new processed media detection, ideal posting cadence, inactivity since the last post, Andrew-provided life/trip context, holiday or culturally relevant moments, sensitive current events relevant to Andrew's travel profile goals, and trend/timing signals that suggest preparing a post before a deadline. See `docs/plans/discord-dm-conversation-orchestration.md` for the DM-first opportunity and trigger plan.

The Discord bot should ultimately guide the entire creator workflow, not just media picking. It should help Andrew decide the post type, choose the strongest media, collect missing factual/creative context, draft stronger hook-first captions, suggest hashtags/location/alt text where supported, schedule posts into a future queue, and preserve the double-approval workflow. The product north star is follower growth from 758 to 5,000 while preserving Andrew's control and taste; growth recommendations should be quality-oriented, auditable, and never use spammy engagement automation.

## Safety invariants

- Do not call Meta publishing endpoints in any Discord selection milestone.
- Do not run `meta validate-carousel-publish --execute` until after Discord selection is implemented, dry-runs are reviewed, and Andrew explicitly approves live publishing in the active session.
- Discord interaction must never mutate source local/NAS photos.
- Discord selection must update only SQLite draft/candidate media state through the same rules as `drafts media-edit`.
- Any material media selection after approval invalidates active approvals and moves the draft back to `needs_edits`.
- Use dry-run/local harnesses before live Discord API calls.
- If Discord media attachments are unreliable, fall back to R2-staged public review URLs or local artifact paths in the message text; do not block selection-state correctness on attachment delivery.
- Never log, commit, or paste Discord bot tokens, Meta tokens, R2 credentials, or signed/private URLs.
- Never fabricate factual details such as exact location, event names, people, or dates; ask Andrew to confirm uncertain context.
- Growth optimization must stay within supported platform behavior: no fake engagement, follow/unfollow automation, comment spam, DM spam, scraping, or browser automation.
- Programmatic Instagram fields must be capability-checked before implementation. Known safe v1 fields include media, caption text, hashtags embedded in caption, and local alt-text/audit metadata; location tagging, collaborators, music, product tags, and other advanced fields need explicit Meta Graph capability validation before being promised or used.

## Milestone A: `feat/discord-selection-model`

**Goal:** Add a local, testable selection-request model that can express "select X photos from Y suggestions" without calling Discord.

**Expected behavior:**
- A draft can produce a Discord selection request containing:
  - draft id,
  - target selection count X,
  - suggested item count Y,
  - numbered candidate media items in current review order,
  - lead/cover guidance,
  - stable command examples or interaction payload metadata.
- The request refuses invalid counts:
  - X must be at least 1,
  - X cannot exceed Y,
  - carousel selections require 2 to 10 photos,
  - single-image selections require exactly 1 photo.
- Applying a selection reuses or wraps `apply_draft_media_selection(...)` so existing validation, ordering, role assignment, and approval invalidation remain the source of truth.
- Tests cover request rendering, count validation, applying a selected set/order, lead selection, and approval invalidation.

**Likely files:**
- Create: `src/post_relay/discord_selection.py`
- Modify: `src/post_relay/cli.py`
- Test: `tests/test_discord_selection.py`
- Maybe update: `README.md`, `AGENTS.md`, `docs/plans/current-agent-roadmap.md`

**Suggested CLI harness:**

```bash
.venv/bin/post-relay drafts discord-selection-plan \
  --draft-id <draft-id> \
  --target-count 5 \
  --db data/post_relay.sqlite

.venv/bin/post-relay drafts discord-selection-apply \
  --draft-id <draft-id> \
  --lead 3 \
  --select 3,7,8,10,12 \
  --post-type carousel \
  --db data/post_relay.sqlite
```

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_discord_selection.py -q
.venv/bin/python -m pytest -q
```

## Milestone B: `feat/discord-selection-payload`

**Goal:** Extend the dry-run Discord payload harness so a selection request can be previewed locally before live bot delivery.

**Expected behavior:**
- A dry-run selection payload lists the Y suggested photos in numbered order and states "select X" clearly.
- The payload includes available preview references:
  - existing local image paths,
  - generated thumbnail/contact-sheet artifact paths when available,
  - missing-file reporting,
  - optional staged review URLs if R2 staging records exist.
- The payload includes the exact interaction semantics the live bot will expose, such as:
  - select menu with numbered labels when Y is within Discord component limits,
  - multiple pages or command fallback when Y exceeds Discord limits,
  - explicit lead/cover selection.
- The payload remains dry-run only and does not call Discord.

**Likely files:**
- Modify: `src/post_relay/discord_preview.py` or create `src/post_relay/discord_selection_payload.py`
- Modify: `src/post_relay/cli.py`
- Test: `tests/test_discord_selection.py` or `tests/test_discord_preview.py`
- Docs: `README.md`, `AGENTS.md`, `docs/plans/current-agent-roadmap.md`

**Suggested CLI harness:**

```bash
.venv/bin/post-relay drafts discord-selection-preview \
  --draft-id <draft-id> \
  --target-count 5 \
  --db data/post_relay.sqlite
```

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_discord_selection.py tests/test_discord_preview.py -q
.venv/bin/python -m pytest -q
```

## Milestone C: `feat/discord-guided-draft-package`

**Goal:** Add a local, testable guided drafting service that turns selected media plus Andrew's answers into a complete growth-oriented post package.

**Expected behavior:**
- Recommend post type with a short rationale: single image, carousel, or reel-planning-only.
- Ask focused questions only when they materially improve the post, including:
  - location/place/trip/date confidence,
  - story angle,
  - mood/tone,
  - audience hook,
  - anything to include or avoid.
- Generate multiple caption options with attention-grabbing first lines/hooks.
- Suggest hashtags as caption text, grouped by broad travel/location/style/niche intent, without overstuffing.
- Suggest location text for Andrew confirmation; do not treat inferred location as fact until confirmed.
- Generate local alt text/accessibility notes even if Instagram Graph cannot publish alt text directly.
- Store draft package fields and rationale in SQLite so later approvals/scheduling/publishing use audited values.
- Include a "why this could grow followers" rationale based on media strength, hook, save/share potential, specificity, and consistency with Andrew's travel-photography identity.

**Likely files:**
- Create: `src/post_relay/guided_drafting.py`
- Modify: `src/post_relay/repository.py` for caption option/context/metadata persistence if needed
- Modify: `src/post_relay/cli.py` for local harness commands
- Test: `tests/test_guided_drafting.py`
- Docs: `README.md`, `AGENTS.md`, `docs/plans/current-agent-roadmap.md`

**Suggested CLI harness:**

```bash
.venv/bin/post-relay drafts guided-package \
  --draft-id <draft-id> \
  --goal "grow andrewhml from 758 to 5000 followers" \
  --db data/post_relay.sqlite
```

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_guided_drafting.py -q
.venv/bin/python -m pytest -q
```

## Milestone D: `feat/instagram-capability-matrix`

**Goal:** Make Post Relay explicit about which Instagram post fields it can publish programmatically and which remain local/review-only.

**Expected behavior:**
- Store or render a capability matrix for supported Meta Graph publish fields:
  - media URLs / carousel children: publishable,
  - caption including hashtags: publishable,
  - local alt text: useful for review/accessibility, publishability must be verified before live use,
  - location tagging: verify current official support before implementing,
  - collaborators, music, product tags, story-specific fields, reel-only fields: out of v1 unless official support is validated.
- Add tests that prevent unsupported metadata from silently being sent to Meta publish endpoints.
- Show unsupported/review-only metadata clearly in Discord so Andrew can still use it manually if needed.
- Keep publish attempts sanitized.

**Likely files:**
- Create: `src/post_relay/instagram_capabilities.py`
- Modify: `src/post_relay/publishing.py`
- Modify: `src/post_relay/discord_preview.py` or selection payload module
- Test: `tests/test_instagram_capabilities.py`, `tests/test_publish_validation.py`

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_instagram_capabilities.py tests/test_publish_validation.py -q
.venv/bin/python -m pytest -q
```

## Milestone E: `feat/discord-selection-bot`

**Goal:** Add live Discord bot interaction for Andrew to select X photos from Y suggestions and persist that selection locally.

**Expected behavior:**
- The bot can send a selection message for a draft to the configured review channel.
- Andrew can choose exactly X items from the Y suggestions.
- Andrew can choose or confirm the lead/cover image.
- The bot records the selected ordered photo numbers and applies them to the draft through the selection service.
- The bot returns a confirmation summary showing:
  - selected count,
  - lead/cover,
  - included photos in final order,
  - excluded photos,
  - whether approvals were invalidated.
- The bot rejects incomplete, too-large, duplicate, or out-of-range selections with actionable feedback.
- Bot authentication/configuration reads secrets only from environment/private `.env` or the configured Hermes/Discord gateway; no secrets in git or output.

**Discord interaction constraints to account for:**
- Discord select menus support a limited number of options, so large Y values need pagination or a command fallback.
- If native image attachments fail, the message should still be actionable via contact sheets, numbered labels, and paths/URLs.
- Selection state must be idempotent enough to tolerate duplicate interaction callbacks.

**Likely files:**
- Create: `src/post_relay/discord_bot.py` or gateway adapter module once the runtime integration is chosen
- Modify: `src/post_relay/config.py` if bot/channel config is local app config
- Modify: `src/post_relay/cli.py` for a local send/simulate command if needed
- Tests: new bot adapter tests with fake Discord interaction payloads
- Docs: `README.md`, `AGENTS.md`, `docs/plans/current-agent-roadmap.md`

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_discord_selection.py -q
.venv/bin/python -m pytest -q
```

Then perform one explicit Discord-only smoke test in the review channel. Do not run Instagram publish execution as part of this milestone.

## Milestone F: `feat/discord-guided-review-bot`

**Goal:** Expand the live Discord bot from media selection into a guided post-building conversation.

**Expected behavior:**
- Guide Andrew through post type, media choice, caption direction, hashtags, location confirmation, alt text, and schedule slot.
- Provide concise recommendations with rationales rather than just open-ended questions.
- Support natural-language revisions such as:
  - "make the hook stronger",
  - "less dramatic",
  - "choose a more iconic cover",
  - "give me three caption options",
  - "schedule this for next Friday morning".
- Persist every accepted decision to the draft record or related audit tables.
- Require explicit draft approval before queueing and explicit publish approval before live publish.
- Confirm when a requested field is local/review-only rather than publishable through Meta Graph.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_discord_selection.py tests/test_guided_drafting.py -q
.venv/bin/python -m pytest -q
```

Then perform one explicit Discord-only guided review smoke test. Do not run Instagram publish execution as part of this milestone.

## Milestone G: `feat/discord-schedule-queue-guidance`

**Goal:** Let the Discord bot guide Andrew from approved draft to scheduled queue while optimizing cadence toward follower growth.

**Expected behavior:**
- Recommend schedule slots based on configured cadence and simple interpretable rules.
- Avoid clustering similar posts or dumping too much backlog at once.
- Ask Andrew to approve or adjust the proposed slot in Discord.
- Persist the chosen schedule with the existing scheduling state machine.
- Request final publish approval near the publish window according to the configured policy.
- Keep all live publish execution behind explicit approval and `--execute`.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_scheduling.py -q
.venv/bin/python -m pytest -q
```

## Milestone H: `feat/live-carousel-publish-smoke-notes`

**Goal:** After Discord photo selection and guided post-package approval are proven, run one explicitly approved live carousel smoke test through the guarded carousel path, preferably using staged-R2 public HTTPS media URLs, and document observed Meta behavior.

**Preconditions:**
- Discord selection flow has selected the final carousel media from a larger suggestion set.
- Discord guided review has confirmed post type, content direction, caption, hashtags, location handling, alt text/review-only metadata, and schedule intent.
- The selected media order and lead/cover have been confirmed in Discord.
- The draft has non-empty approved caption/content.
- Draft approval and final publish approval are active after any media selection changes.
- R2 staging upload dry-run and execute have produced uploaded staged `draft_media` records, or manual public HTTPS URLs have been verified.
- `meta validate-carousel-publish --from-staged-r2 --dry-run` has been reviewed.
- Andrew explicitly authorizes `--execute` in the active session.

**Verification after live publish:**

```bash
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup \
  --draft-id <draft-id> \
  --config config/photo_sources.yaml \
  --db data/post_relay.sqlite
.venv/bin/python -m pytest -q
```

Record sanitized child container ids, carousel container id, status, published media id, final draft status, and any Meta account/app limitations in `docs/plans/current-agent-roadmap.md`.

## Acceptance checklist before any Instagram live carousel smoke test

- [ ] Local selection model tests pass.
- [ ] Dry-run Discord selection payload is reviewed.
- [ ] Live Discord selection smoke test succeeds without touching Meta publishing endpoints.
- [ ] Guided Discord review confirms post type, media, hook/caption, hashtags, location treatment, alt text/review-only metadata, and schedule intent.
- [ ] Andrew confirms final selected carousel images and lead/cover in Discord.
- [ ] Any approval invalidation caused by media changes has been resolved with fresh draft and publish approvals.
- [ ] Staged-R2 or manual public HTTPS image URLs are dry-run validated.
- [ ] Andrew explicitly approves live `--execute` in the active session.
