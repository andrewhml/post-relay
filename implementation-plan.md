# Post Relay — Implementation Plan

## Status
Draft v0.1

## Purpose
This document breaks Post Relay into concrete implementation phases and tasks.

It assumes the currently validated setup:
- target Instagram account: `andrewhml`
- account type: Creator
- linked Facebook Page: `Andrewhml`
- Meta app: `Post Relay`
- primary integration route: `graph.facebook.com` with Page-linked Instagram account access
- initial product scope: single-account v1

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

## Recommended Next Build Artifact
After this plan, the most useful next detailed artifact is:
- `data-model.md`

## Practical Next Human Steps
Andrew should continue with:
- keeping tokens private and rotating any exposed test tokens
- identifying the final set of permissions actually needed
- pausing on app publication/review until publish testing requires it

## Immediate Next Engineering Step
After this milestone, continue with controlled single-image publish validation behind the existing local draft/publish approval safeguards. Preconditions: Andrew explicitly provides local token environment variables, picks a safe test image/caption, and confirms the target account. Use the sanitized read-only Meta Graph client as the base, keep secrets redacted, and do not add autonomous publishing. The repo-level current roadmap is maintained in `docs/plans/current-agent-roadmap.md`; future agents should read `AGENTS.md` first, then the roadmap before implementing.
