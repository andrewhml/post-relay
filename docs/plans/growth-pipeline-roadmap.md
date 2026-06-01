# Growth Pipeline Roadmap

## Status

Current product-direction planning document. Created after the recommendation-engine work began surfacing durable account preferences and Instagram-native growth guidance. This is a docs-first milestone: it defines where Post Relay should go before adding new data fields, commands, gateway jobs, or GUI surfaces.

This roadmap should be read with:

- `docs/plans/recommendation-engine-roadmap.md`
- `docs/plans/current-agent-roadmap.md`
- `docs/plans/product-onboarding-roadmap.md`
- `AGENTS.md`

## Product promise

Post Relay should become a goal-driven content operating system for creator and business accounts:

> Users state what they want an account to become. Post Relay helps maintain a reviewed content pipeline toward that goal, learns from account/post data, and proactively nudges when the pipeline is weak.

The product should not become a passive analytics dashboard. It should answer:

1. What should I do next?
2. Why does that support the account goal?
3. What evidence supports it?
4. What is blocked in the pipeline?
5. What can the agent prepare next?
6. What should the user review or decide?

## Core principles

1. **Planning plus evidence beats metrics alone.** Analytics are useful only when they change recommendations, cadence planning, experiments, or pipeline health.
2. **Creative control stays with the user.** The system can recommend safe/growth/stretch paths, but it must not publish, schedule, approve, or rewrite without explicit scoped commands.
3. **Platform guidance is a prior, not a command.** Instagram-native guidance such as reels cadence, carousel reach, hooks, captions, places/topics, audio, and quality baselines should be visible and test-covered before it becomes scoring.
4. **Local-first remains the default.** Recommendation and planning surfaces should consume stored local state and make no network calls by default.
5. **Other users must be first-class.** Account behavior, goals, cadence, check-in preferences, comfort-zone settings, and growth posture belong in app data structures, not Andrew-specific Hermes memory.

## Layer 1: account goal and posture

The active goal artifact already gives the agent a north star. The next evolution is an account posture profile that determines how strongly the agent should optimize for growth, consistency, sales/leads, education, portfolio quality, or personal sharing.

Potential durable fields:

```text
goal_type: growth | sales_leads | education | portfolio | community | personal_archive | fun
growth_mode: conservative | balanced | growth_push | experimental
primary_success_metric: followers | saves | shares | comments | dms | profile_visits | website_clicks | sales_leads | cadence | satisfaction
target_monthly_reels: integer | null
target_monthly_carousels: integer | null
target_weekly_posts: integer | null
agent_checkin_cadence: daily | twice_weekly | weekly | monthly | goal_adaptive | off
comfort_zone_push_enabled: boolean
max_push_level: low | medium | high
preferred_growth_experiments: list[str]
blocked_growth_experiments: list[str]
```

Default posture should be conservative/balanced unless the user chooses a stronger push. Andrew's current travel-account direction likely maps to `goal_type=growth`, `growth_mode=growth_push`, a save/share/follower-oriented metric set, and medium comfort-zone push.

## Layer 2: account and post evidence

Post Relay should treat account data as evidence for better planning, not as dashboard decoration.

### Account snapshots

Periodic read-only snapshots can include:

```text
followers_count
follows_count
media_count
profile_views, if available
website_clicks, if available
aggregate reach/impressions, if available
snapshot_time
```

Use cases:

- detect follower-growth plateaus
- compare follower movement to cadence
- inform weekly/monthly reviews
- drive check-ins only when useful

### Post performance snapshots

For each published post, store and summarize:

```text
post_type
published_at
caption traits
media count
location tag presence
reel audio presence, if supported/known
first-slide text presence, if supported/known
hashtag count
reach
likes
comments
saves
shares
profile visits, if available
follows, if available
watch time or retention, if available for reels
```

Use cases:

- compare formats against goals
- learn which caption/hook patterns work
- identify repeatable content pillars
- measure experiments without overclaiming causality

### Pipeline state

The operational content pipeline should be explicit enough for CLI, agent check-ins, and a future GUI:

```text
idea
candidate
selection_review
crop_review
copy_review
final_review
approved
scheduled
published
analytics_due
learned_from
```

Use cases:

- know what is blocked
- know whether cadence is at risk
- identify agent-preparable work
- prioritize user review asks

### Experiments

Growth pushes should be measurable as experiments instead of generic advice:

```text
experiment_type: reel_cadence_push | carousel_text_overlay | direct_cta | posting_cadence | topic_keyword_test | location_topic_discovery
hypothesis
target_window
target_count
actual_count
status
result
notes
```

This lets Post Relay say, for example: "The 10 reels/month target is behind pace, but route carousels are currently getting stronger saves, so the next growth move should test one reel from a route-ready sequence rather than blindly replacing carousels."

## Layer 3: recommendation and planning surfaces

Recommendations should be multi-path instead of one generic answer.

### Safe path

The safest next move based on readiness, source truth, current workflow state, and review gates.

### Growth path

The move most likely to support the account goal based on platform priors plus local evidence.

### Stretch path

A deliberate comfort-zone push with clear tradeoffs.

Each recommendation should render:

```text
Goal supported
Evidence used
Platform prior vs local evidence distinction
Comfort-zone delta: low | medium | high
Risk/tradeoff
Next safe command
No-network/no-mutation statement
```

Candidate scoring should eventually separate dimensions instead of collapsing everything into one number:

```text
readiness_score
visual_quality_score
goal_alignment_score
growth_potential_score
comfort_zone_delta
risk_score
learning_value_score
```

## Layer 4: proactive agent cadence

Scheduled or gateway-based check-ins should come after local planners are useful and after the user opts in.

Potential check-in types:

```text
pipeline_gap
post_due
analytics_learning
content_idea
growth_challenge
approval_reminder
monthly_review
```

Example trigger:

```text
Goal: 10 reels/month
Published reels: 2
Scheduled reels: 1
In-review reels: 0
Days left: 18
Gap: 7 reels
Recommended check-in: ask whether the user wants 3 reel candidates from processed photos.
```

The agent should message only when there is useful, specific context. Avoid timer spam.

## Layer 5: future GUI

The future GUI should visualize live product state rather than duplicate docs.

Suggested views:

### Pipeline board

Columns:

```text
Ideas
Candidates
Selection
Crop
Copy
Final review
Scheduled
Published
Learning
```

Card fields:

```text
title
format
goal alignment
growth value
status
blocker
scheduled date
analytics due date
```

### Calendar view

Show scheduled posts, cadence gaps, target vs actual, and planned formats by week.

### Goal dashboard

Show follower/content cadence, best-performing formats/topics, experiments in progress, and pipeline health.

### Recommendation inbox

Show agent-proposed actions such as:

- Need two more reels this week.
- This Kyoto set is the best reel candidate.
- Route carousels are getting saves; repeat that pattern.
- A post is blocked on final copy review.

## Milestone sequence

### Milestone 1: `docs/growth-pipeline-roadmap`

Delivered by this document. No runtime behavior changes.

Acceptance:

- Defines the long-term product architecture.
- Names the durable data areas needed for growth-pipeline planning.
- Defines safe/growth/stretch recommendation paths.
- Establishes that scheduled check-ins are opt-in and planner-first.
- Updates repo handoff surfaces so future agents find this roadmap.

Verification:

```bash
.venv/bin/python -m pytest -q
```

### Milestone 2: `feat/growth-posture-preferences` (completed in this branch)

Add durable account-level planning preferences without changing live side effects.

Delivered:

- Extended account preferences with goal/posture/cadence/check-in/comfort-zone fields:
  - `goal_type`
  - `growth_mode`
  - `primary_success_metric`
  - `target_monthly_reels`
  - `target_monthly_carousels`
  - `target_weekly_posts`
  - `agent_checkin_cadence`
  - `comfort_zone_push_enabled`
  - `max_push_level`
  - `preferred_growth_experiments`
  - `blocked_growth_experiments`
- Versioned preference changes include those growth posture fields.
- `preferences set`, `preferences show`, and `preferences agent-brief` render the growth posture alongside review-order and copy-collaboration preferences.
- Caption-style recommendations include compact growth posture guidance as local advisory context.
- No Discord, R2, Meta, schedule, approval, post lifecycle, opportunity, publish-attempt, or analytics mutations.

Verification:

```bash
.venv/bin/python -m pytest tests/test_account_preferences.py tests/test_recommendation_signals.py -q
.venv/bin/python -m pytest -q
```

### Milestone 3: `feat/growth-coach-recommendations` (completed in this branch)

Adds a local/no-network command:

```bash
post-relay recommendations growth-coach --db data/post_relay.sqlite
```

Delivered output:

- active goal
- account posture
- cadence target and current month/week gap
- safe path
- growth path
- stretch path
- comfort-zone delta per path
- evidence used
- warnings from sparse local evidence
- next safe command per path
- explicit no-network/no-mutation statement

Verification:

```bash
.venv/bin/python -m pytest tests/test_recommendation_signals.py::test_build_growth_coach_recommendations_uses_goal_posture_and_local_evidence tests/test_recommendation_signals.py::test_render_growth_coach_recommendations_is_advisory_and_actionable tests/test_recommendation_signals.py::test_cli_recommendations_growth_coach_is_local_advisory_only -q
.venv/bin/python -m pytest -q
```

### Milestone 4: `feat/pipeline-health`

Add a local/no-network command:

```bash
post-relay pipeline health --db data/post_relay.sqlite
```

Initial output:

- counts by pipeline stage
- blocked posts/tasks
- cadence risk
- user-needed reviews
- agent-preparable next work
- no-network/no-mutation statement

### Milestone 5: `feat/agent-checkin-plan`

Add a no-network planner before cron/gateway automation:

```bash
post-relay agent checkin-plan --db data/post_relay.sqlite
```

Initial output:

- recommended check-in cadence
- trigger reason
- draft message
- user action requested
- why it is useful now
- explicit statement that no message was sent

### Milestone 6: opt-in scheduled check-ins

Only after the local planner is useful and the user authorizes it:

- create/update Hermes cron or gateway job
- send only specific, useful check-ins
- keep publish/schedule/approval actions separate
- report when no useful check-in exists rather than sending filler

### Milestone 7: analytics learning loop

Use stored post/account data to answer:

- What worked?
- What should be repeated?
- What should be stopped?
- Which experiment is inconclusive?
- What should be tried next?

## Safety rules

- Growth-pipeline commands are local-first and advisory by default.
- They must not send Discord messages, upload to R2, delete R2 objects, call Meta publish routes, approve content, approve publishing, schedule posts, mutate draft lifecycle state, or create publish attempts.
- Read-only analytics collection remains separate and explicit behind `--execute`; recommendation/planning commands consume stored local snapshots.
- Do not fabricate facts from filenames, folders, images, or model guesses. Label assumptions.
- Do not optimize for growth at the expense of the user's taste, source-media truth, or review safety.
- Do not convert Instagram platform priors into hidden scoring or automation before they are personalized against active goals, local feedback, and stored analytics.
- Proactive gateway behavior must remain opt-in, scoped, and separable from publishing/scheduling/approval side effects.

## Open questions

- Which preference fields belong in `account_preferences` versus a separate account strategy table?
- Should experiments be first-class tables immediately or emerge from recommendation logs?
- What is the minimum useful pipeline-stage model before building GUI surfaces?
- How should the app represent comfort-zone deltas without making users feel judged?
- What cadence of check-ins is useful for growth without becoming noise?
