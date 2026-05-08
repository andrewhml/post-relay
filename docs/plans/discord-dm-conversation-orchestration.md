# Discord DM Conversation Orchestration Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Use one rollback-safe branch and PR per milestone.

**Goal:** Make Post Relay a private Discord DM-first content collaborator where either Andrew or the agent can initiate a conversation about creating a new Instagram post.

**Architecture:** Keep Post Relay local-first and approval-gated. Add a conversation/opportunity layer above the existing candidate, draft, selection, guided package, schedule, and publish-approval services. The Discord bot should talk primarily through Andrew's private DM, while local deterministic services decide when a post opportunity exists and what safe next action to propose. Agent-initiated outreach should create suggestions and DM prompts only; it must never publish, schedule, or mutate approved content without Andrew's explicit confirmation.

**Tech Stack:** Python 3.9+, SQLite, Typer, pytest, existing Post Relay services, Discord DM bot/interactions, scheduled/background checks, optional future web/current-events/trend data adapters.

---

## Product decision

The primary Discord surface should be Andrew's private DM with the agent, not a public or semi-public review channel. The bot should support two initiation paths:

1. Andrew-initiated: Andrew can DM the agent at any time with a request like "start a post from the Kyoto night market set" or "I want to post something about this trip" and provide as much context as he has.
2. Agent-initiated: Post Relay can detect a reason to collaborate on a post and DM Andrew with a concise, actionable prompt.

The agent's job is to start the right conversation at the right time, collect or infer only safe context, propose a high-quality post package, and preserve Andrew's control.

## Agent-initiated opportunity triggers

Each trigger should produce a local `post_opportunity` record before it sends any Discord DM. DMs should be rate-limited, deduplicated, and easy for Andrew to dismiss.

Initial trigger families:

- New media detected in configured processed media folders.
  - Example: new processed folder appears under the Lightroom/year source.
  - Suggested action: "I found 12 new processed photos from this folder. Want to pick 5 for a carousel?"
- Posting cadence/growth interval.
  - Example: a configured ideal interval since last feed post has elapsed.
  - Suggested action: "It's been N days since the last post. Want to prep a carousel from the backlog?"
- Inactivity threshold.
  - Example: Andrew has not posted for longer than the maximum healthy cadence window.
  - Suggested action: prioritize low-friction candidate groups with strong visual variety.
- User life event or trip context.
  - Example: Andrew tells the agent about an active trip, upcoming trip, event, or activity.
  - Suggested action: create a contextual post thread and ask for factual details only when needed.
- Calendar/holiday/cultural event relevance.
  - Example: holiday, travel season, local event, or cultural moment that aligns with Andrew's travel photography goals.
  - Suggested action: suggest a relevant backlog or current-media post angle.
- Current-events or industry-specific relevance.
  - Example: a peace deal in the West Bank or another travel/geopolitical/cultural topic that materially affects how travel content should be framed.
  - Suggested action: propose a sensitive, context-aware post or recommend holding/adjusting content if posting could feel tone-deaf.
- Trend/timing data.
  - Example: trend data suggests a post should be drafted before a specific time window.
  - Suggested action: DM Andrew with the deadline, rationale, and one-tap options to start, snooze, or dismiss.

## Conversation principles

- DM-first: send private DMs by default. Public channels should be optional later, never the default review surface.
- One active post thread at a time unless Andrew explicitly starts another.
- Every agent-initiated DM must explain why now in one sentence.
- Every prompt should offer concrete options, not a vague open-ended ask.
- Andrew can provide context in natural language at any time; the bot should attach that context to the active opportunity/draft.
- The bot must distinguish facts from guesses. Unconfirmed locations, dates, people, events, and claims remain questions or review-only notes.
- Growth suggestions must be auditable and taste-preserving: no fake engagement, spam, scraped personal data, or manipulative automation.
- Instagram publish capability rules still apply. The DM can discuss review-only metadata, but only capability-checked fields can be sent through Meta publish endpoints.

## Safety invariants

- Do not call Meta publishing endpoints from DM conversation milestones.
- Do not run `meta validate-carousel-publish --execute` from any Discord DM milestone.
- Agent-initiated DMs are suggestions only; they cannot create a live post without Andrew's explicit draft and publish approvals.
- Never log, commit, or paste Discord bot tokens, Meta tokens, R2 credentials, signed URLs, or private message contents beyond sanitized local audit records.
- Do not ingest sensitive current-event/trend data into a post without clear source attribution and Andrew confirmation.
- If a contextual event is sensitive, the bot should prefer caution and ask Andrew whether the angle is appropriate.
- Source local/NAS media remains immutable.
- Material media/content edits still invalidate active approvals.

## Data model direction

Add small local records rather than embedding conversation state only in Discord messages:

- `post_opportunities`
  - id
  - trigger_type, e.g. `user_dm`, `new_media`, `cadence_due`, `inactivity`, `life_event`, `holiday_event`, `current_event`, `trend_window`
  - trigger_key for dedupe, e.g. source folder path hash, date window, event id, trend id
  - title/summary
  - rationale
  - status, e.g. `new`, `dm_sent`, `dismissed`, `converted_to_draft`, `snoozed`
  - candidate_group_id nullable
  - draft_id nullable
  - due_at / expires_at nullable
  - created_at / updated_at

- `conversation_threads`
  - id
  - opportunity_id nullable
  - draft_id nullable
  - discord_channel_id or DM conversation id stored in sanitized/non-secret form
  - status, e.g. `active`, `waiting_for_user`, `closed`
  - last_prompt_summary
  - created_at / updated_at

Keep raw Discord message content minimal in the database. Persist durable decisions and sanitized summaries, not private chat transcripts unless Andrew explicitly chooses that later.

## Milestone A: `feat/discord-dm-opportunity-model`

**Goal:** Add local models/services for post opportunities and DM conversation state without calling Discord.

**Expected behavior:**
- A user-initiated DM can be represented as a `user_dm` opportunity.
- Agent triggers can create deduped opportunities with rationale and suggested next action.
- Opportunities can be dismissed, snoozed, or converted to an existing/new draft.
- The service refuses duplicate active opportunities for the same trigger key.
- Tests cover each trigger type Andrew named: new media, cadence due, life/trip event, holiday/current event, inactivity, and trend window.

**Likely files:**
- Create: `src/post_relay/post_opportunities.py`
- Modify: `src/post_relay/db.py`
- Modify: `src/post_relay/repository.py`
- Modify: `src/post_relay/cli.py` for a local harness such as `opportunities create/list/dismiss`
- Test: `tests/test_post_opportunities.py`
- Docs: `README.md`, `AGENTS.md`, `docs/plans/current-agent-roadmap.md`

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_post_opportunities.py -q
.venv/bin/python -m pytest -q
```

## Milestone B: `feat/discord-dm-intake-harness`

**Goal:** Add a no-network local harness that turns Andrew's DM-style text into a post opportunity or draft-context update.

**Expected behavior:**
- A local command can simulate Andrew saying: "start a post about my Kyoto night market photos. Make it cinematic and less touristy."
- If no draft exists, the harness creates or links an opportunity and suggests candidate groups to choose from.
- If a draft/conversation is active, the harness records durable context and routes to the next safe step: media selection, guided package, schedule, or approval.
- The harness returns concise DM-style copy with next options.
- Tests verify private-DM copy does not expose secrets or private local paths unless explicitly in local-only CLI output.

**Likely files:**
- Create: `src/post_relay/dm_intake.py`
- Modify: `src/post_relay/cli.py`
- Test: `tests/test_dm_intake.py`

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_dm_intake.py -q
.venv/bin/python -m pytest -q
```

## Milestone C: `feat/discord-dm-selection-bot`

**Goal:** Adapt the live Discord selection bot milestone so selection happens in Andrew's private DM.

**Expected behavior:**
- The bot sends selection prompts to Andrew's DM, not the review channel by default.
- Andrew can start selection from a DM command or by replying to an agent-initiated opportunity.
- Andrew can choose exactly X items from Y suggestions and confirm lead/cover.
- The bot applies selection through the existing local selection service.
- The bot confirms selected count, lead/cover, included order, excluded photos, and approval invalidation in DM.
- Invalid selections get actionable DM feedback.
- Live smoke test is Discord-only and private-DM-only. It must not call Meta publish endpoints.

**Likely files:**
- Create/modify Discord adapter module selected by the implementation milestone.
- Reuse: `src/post_relay/discord_selection.py`
- Reuse: `src/post_relay/discord_preview.py`
- Tests: fake Discord DM interaction payload tests.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_discord_selection.py tests/test_discord_selection_payload.py -q
.venv/bin/python -m pytest -q
```

Then perform one explicit Discord-only private DM smoke test. Do not run Instagram publish execution as part of this milestone.

## Milestone D: `feat/opportunity-trigger-checks`

**Goal:** Add safe local trigger checks for agent-initiated post suggestions.

**Expected behavior:**
- New-media check scans indexed/candidate data and creates opportunities for newly available candidate groups.
- Cadence/inactivity check uses local post/draft history and configurable intervals.
- Life/trip/event checks can be manually seeded first; external calendar/current-event adapters are future optional additions.
- Trend-window checks start as manual/imported records unless an explicit trusted data source is added later.
- Trigger checks create opportunities but do not DM unless DM sending is enabled and rate limits pass.
- Tests cover dedupe, rate limiting, snooze, and dismissal.

**Likely files:**
- Create: `src/post_relay/opportunity_triggers.py`
- Modify: `src/post_relay/cli.py` for `opportunities scan --dry-run`
- Test: `tests/test_opportunity_triggers.py`

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_opportunity_triggers.py -q
.venv/bin/python -m pytest -q
```

## Milestone E: `feat/discord-dm-guided-review`

**Goal:** Expand private DM conversations from media selection into the full guided post-building workflow.

**Expected behavior:**
- Guide Andrew through post type, selected media, hook-first caption, hashtags, location treatment, local alt text/accessibility notes, schedule slot, draft approval, and publish approval request.
- Support Andrew-provided context and revisions in natural language.
- Keep all decisions auditable and persisted locally.
- Confirm review-only versus publishable fields using the Instagram capability matrix.
- Keep final publish execution outside this milestone.

**Verification:**

```bash
.venv/bin/python -m pytest tests/test_guided_draft.py tests/test_instagram_capabilities.py -q
.venv/bin/python -m pytest -q
```

## Open implementation questions

Resolve these at implementation time with local tests before live Discord calls:

- Which Discord runtime owns the DM bot process: a Post Relay process, Hermes gateway integration, or a thin adapter around the existing Discord agent setup?
- How should Andrew's Discord user id be configured privately so the bot only DMs the intended person?
- How often should cadence/inactivity/trend checks run, and where should scheduler state live?
- Which current-event/trend sources are trustworthy enough for suggestions, and how should the bot cite them?
- What is the maximum number of agent-initiated DMs per day/week?

## Acceptance checklist before any Instagram live carousel smoke test

- [ ] Private DM opportunity model exists and is tested.
- [ ] Andrew can initiate a post conversation by DM.
- [ ] The agent can create a local opportunity for new media, cadence/inactivity, trip/life context, event/current-event relevance, or trend timing.
- [ ] Agent-initiated opportunities are deduped, rate-limited, dismissible, and snoozable.
- [ ] Live Discord private DM selection smoke test succeeds without touching Meta publishing endpoints.
- [ ] Guided DM review confirms post type, media, hook/caption, hashtags, location treatment, alt text/review-only metadata, schedule intent, and approvals.
- [ ] Any approval invalidation caused by media/content changes has been resolved with fresh approvals.
- [ ] Andrew explicitly approves any later live `--execute` publish in the active session.
