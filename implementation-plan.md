# Post Relay — Implementation Plan

## Status
Current roadmap snapshot after read-only insights storage and recommendation feedback summaries landed, with follower-growth tracking implemented on the current `feat/follower-growth-tracking` branch. This file is historical; the canonical, actively maintained agent plan is `docs/plans/current-agent-roadmap.md`.

## Purpose
This document breaks Post Relay into concrete implementation phases and tasks.

It assumes the currently validated setup:
- target Instagram account: `andrewhml`
- account type: Creator
- linked Facebook Page: `Andrewhml`
- Meta app: `Post Relay`
- primary integration route: `graph.facebook.com` with Page-linked Instagram account access
- initial product scope: single-account v1

## Current Engineering Snapshot
Post Relay has now implemented most feed/carousel production hardening through the open PR #55 branch:
- local SQLite content/draft pipeline, candidate grouping, context questions, approvals, scheduling, and publish approval
- review artifacts, numbered media selection, R2 staging plans/uploads/cleanup, staged-R2 publish URL resolution, and publish export profiles
- sanitized Meta Graph read-only validation, live-proven single-image publishing, live-proven carousel publishing, schedule enforcement, final Meta-bound preview, and explicit resolved `location_id` support
- private Discord DM user-initiated intake, media selection, guided review, scheduling, and double-confirmed local publish approval
- local agent-initiated opportunity records and safe no-network trigger checks
- broad DM request guardrails that ask for narrowing before huge weak matches
- bounded review artifact planning that blocks oversized full contact sheets until Andrew narrows the set
- local semantic DM candidate matching from folder/year/filename descriptors with simple explainable aliases
- local post-publish snapshots, guarded read-only insight metric storage behind explicit `analytics insights-fetch --execute`, advisory local recommendation feedback summaries, and local follower-growth snapshots/summaries toward the 5,000 follower goal

Remaining near-term gaps are targeted optimization and operating-loop gaps, not generic scaffolding: use deterministic recommendation feedback plus local follower-growth summaries as the advisory baseline, then decide whether to prioritize more user-initiated DM practice, proactive opportunity DMs, video/reel validation, or deeper media discovery/enrichment.

## Build Strategy

Build in layers so we prove the workflow before we trust live publishing.

Order of truth:
1. content planning
2. review and approvals
3. queue and scheduling
4. publishing integration
5. optimization

## Phase 0 — Lock known setup facts
### Goals
Capture the working Meta assumptions and IDs in project config/docs without storing secrets.

### Tasks
- Record App ID in local non-secret config/docs
- Record Facebook Page ID: `998312870038313`
- Record Instagram Account ID: `17841400498120050`
- Record that the Creator account path is working through `graph.facebook.com`
- Record that `graph.instagram.com` returned `Invalid platform app` in this setup
- Document required permission families already observed:
  - instagram_basic
  - instagram_content_publish
  - instagram_manage_comments
  - instagram_manage_insights
  - pages_show_list
  - pages_read_engagement

### Deliverables
- updated docs
- local config template

## Phase 1 — Local content model and draft pipeline
### Goals
Create the internal draft/queue system without live publishing.

### Tasks
- define post record schema
- define state machine in code
- create storage directories for posts, logs, queue, cache, config
- create media ingestion module for local folders
- extract metadata from images/videos
- create candidate builder for:
  - single image
  - carousel
  - reel candidate
- create context model for factual + creative inputs
- create interview question model for missing context

### Deliverables
- local post records
- candidate generation flow
- metadata extraction output
- missing-context detection

## Phase 2 — Draft generation and Discord review loop
### Goals
Make Post Relay useful before publishing exists.

### Tasks
- generate caption drafts
- generate hashtag suggestions
- generate location suggestions/unknown markers
- generate post-type recommendations
- generate schedule suggestions
- build rich structured Discord preview format
- support natural-language revision flow
- support explicit draft approval capture
- store revision history

### Deliverables
- working preview message format
- draft/revision loop
- draft approval recording

## Phase 3 — Queue and publish-approval workflow
### Goals
Operationalize scheduling safely.

### Tasks
- add queue manager
- add schedule model and posting windows
- implement double approval state transitions
- add publish-approval request flow in Discord
- add safeguards for changed drafts invalidating prior approvals
- log approval timestamps and source messages when available

### Deliverables
- queue system
- scheduled states
- publish approval workflow

## Phase 4 — Meta integration wrapper
### Goals
Build the API client layer around the actual validated route.

### Tasks
- build Graph API client wrapper for `graph.facebook.com`
- add token loading from secure local environment/config
- add helper methods for:
  - reading Page info
  - resolving linked Instagram account
  - reading IG media
- define publish-related helper methods based on verified Graph route requirements
- validate exact endpoint mechanics for create/publish flow on the linked Instagram account
- add safe request/response logging that strips tokens

### Deliverables
- API client module
- secure config pattern
- sanitized logging

## Phase 5 — Controlled publish test
### Goals
Prove end-to-end publishing with minimal risk.

### Tasks
- verify current publish/create endpoint path for the linked IG account
- verify required parameters for image publish container creation
- create one controlled single-image publish test
- verify result appears on `andrewhml`
- capture remote ids/statuses in logs
- document any Creator-specific limitations discovered

### Deliverables
- successful test publish or clear documented blocker
- publish procedure notes

## Phase 6 — Carousel and reel support
### Goals
Expand beyond the simplest publish path.

### Tasks
- validate carousel creation requirements
- implement carousel draft -> publish flow
- validate reel/video flow for this account/app setup
- implement reel publishing only after successful validation
- add format-specific failure handling

### Deliverables
- carousel publish support
- reel support if validated

## Phase 7 — Learning and optimization
### Goals
Make Post Relay smarter over time.

### Tasks
- record engagement metrics where available
- track approval/revision patterns
- adapt schedule recommendations
- adapt caption-style recommendations
- improve post-type recommendations
- reduce unnecessary interview questions via prior context

### Deliverables
- recommendation improvements
- engagement-informed suggestions

## Technical Work Items
### Storage
- create `data/instagram/posts/`
- create `data/instagram/logs/`
- create `data/instagram/cache/`
- create `data/instagram/config/`
- create secure local env/secret loading strategy

### Core modules
- `media-scanner`
- `candidate-builder`
- `context-engine`
- `interview-engine`
- `draft-generator`
- `discord-presenter`
- `approval-manager`
- `queue-manager`
- `meta-client`
- `publisher`
- `audit-logger`

### Safety requirements in implementation
- never log tokens
- never publish without publish approval
- invalidate stale approvals after material draft changes
- fail visibly on API errors
- keep audit history for all state transitions

## Recommended Next Build Artifacts
The next useful detailed artifacts are now:
- `docs/plans/current-agent-roadmap.md` Later milestones for private-DM operating-loop improvements, proactive opportunity DM controls, video/reel validation, and deeper media discovery/enrichment
- a later video/reel validation plan after feed/carousel cadence is stable
- a later plan for turning enough advisory feedback/follower-growth snapshots into stronger deterministic recommendations

## Practical Next Human Steps
Andrew should continue with:
- keeping tokens private and rotating any exposed test tokens
- using private DM-driven sessions to prove the user-initiated workflow on real travel sets
- collecting read-only insights only with `analytics insights-fetch --execute` when the active token has the needed insights permission
- collecting read-only follower metrics only with `analytics follower-fetch --execute` when explicitly intended; dry-run remains the default
- treating recommendation and follower-growth feedback as advisory until several real posts and account snapshots provide enough signal

## Immediate Next Engineering Step
Finish and merge `feat/follower-growth-tracking`, then choose the next rollback-safe milestone from `docs/plans/current-agent-roadmap.md`, likely more private-DM operating-loop practice, proactive opportunity DM controls, video/reel validation, or deeper local media discovery/enrichment. Keep recommendation and follower-growth feedback advisory-only until several real posts and account snapshots provide enough signal.
