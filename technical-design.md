# Instagram Travel Content Tool — Technical Design

## Status
Historical design, updated after PR #55 was opened. The implementation now uses Python, Typer, SQLite, local processed folders, generated artifacts/exports, optional R2 staging, and official Meta Graph routes. The canonical active plan is `docs/plans/current-agent-roadmap.md`.

## Purpose
This document translates the product requirements into a buildable system design for **Post Relay**, an Instagram travel-content workflow built around the official Meta/Instagram publishing path.

Primary objective:
- help Andrew turn a large local backlog of travel media into high-quality Instagram posts
- keep review and approvals in Discord
- publish only through the official/supported Meta route
- preserve strong human control over anything that goes live

## Design Goals
- Official Meta/Instagram integration only for publishing
- Human-in-the-loop review and approval
- Local-first media ingestion
- Natural-language collaboration in Discord
- Reliable audit trail for drafts, approvals, schedules, and publishing
- Modular enough to add analytics and smarter recommendations later

## Non-Goals for Initial Version
- Unofficial browser automation
- Password-based scraping or posting
- Autonomous posting without explicit publish approval
- Aggressive engagement automation or spam tactics
- Complex dashboard UI before the workflow is proven

## High-Level Architecture
The system should be split into six logical layers:

1. **Media Intake Layer**
   - scans local folders
   - reads image/video metadata
   - groups related media
   - creates draft candidates

2. **Content Intelligence Layer**
   - evaluates candidate media
   - determines likely post type
   - detects missing context
   - drives interviews when necessary
   - drafts captions, hashtags, and metadata

3. **Workflow/State Layer**
   - stores post records
   - tracks states and transitions
   - records approvals, edits, and scheduling

4. **Discord Interaction Layer**
   - sends rich structured previews
   - supports natural-language revision requests
   - handles approval confirmations

5. **Publishing Layer**
   - manages Meta authentication
   - uploads/publishes via Instagram Graph API
   - handles retries, failures, and logging

6. **Learning/Optimization Layer**
   - stores feedback and engagement results
   - improves scheduling suggestions
   - improves content-type and caption recommendations over time

## System Components

### 1. Media Library Scanner
**Responsibilities**
- scan configured local source directories
- enumerate supported media files
- calculate stable file identifiers
- extract available metadata
- identify possible grouped sets (same date, same folder, same sequence)

**Supported inputs**
- JPEG/PNG/HEIC if usable in workflow
- MP4/MOV and other publishable video formats after compatibility validation

**Extractable metadata**
- filename
- file path
- file creation/modification timestamps
- EXIF capture date/time if present
- camera make/model when present
- image orientation and dimensions
- video duration/resolution if present

**Known limitation**
- Sony A7IV source images are not expected to contain GPS data by default, so location usually must come from user interview, folder naming, or later manual entry.

### 2. Candidate Builder
**Responsibilities**
- create candidate single-image posts
- create candidate carousel sets from related files
- identify reel-capable clips or mixed-media groupings
- rank candidate quality using heuristics

**Early heuristics**
- portrait assets may be favored for certain formats
- similar timestamps/folder grouping may imply carousel candidates
- avoid near-duplicate media in the same candidate set
- prefer stronger lead image for carousel cover

**Outputs**
Each candidate should produce a draft seed record with:
- candidate id
- source file list
- likely post type
- confidence level
- unresolved questions

### 3. Context Engine
**Responsibilities**
- aggregate all available context before drafting
- detect missing factual or creative information
- decide whether to draft immediately or interview Andrew first

**Context sources**
- file metadata
- folder names
- prior interview responses
- trip-level notes if added later
- previous post decisions
- explicit user instructions in Discord

**Decision rule**
If confidence is high enough to produce a useful first draft, proceed.
If confidence is low or ambiguity meaningfully reduces quality, ask focused questions.

### 4. Interview Engine
**Responsibilities**
- ask targeted follow-up questions in Discord
- minimize question count
- store answers as structured context
- resume drafting after answers arrive

**Question strategy**
- ask factual questions first when facts are missing
- ask creative questions only when they materially improve the draft
- use lightweight mode by default
- escalate to deeper questioning only for strong/high-priority content

**Examples of stored interview fields**
- place_name
- city
- country
- trip_name
- approximate_date
- mood
- story_angle
- people_involved
- keywords_to_include
- things_to_avoid

### 5. Draft Generator
**Responsibilities**
- generate one or more caption options
- generate hashtags
- propose location text
- propose post type and posting window
- produce rationale and confidence notes

**Draft package output**
Each draft should include:
- draft id
- source files
- preview assets/paths
- post type suggestion
- caption options
- selected primary caption
- hashtags
- location suggestion
- schedule suggestion
- confidence notes
- unresolved questions

### 6. Review Presenter (Discord Layer)
**Responsibilities**
- send a structured but lightweight preview in Discord
- attach/preview images where feasible
- summarize the post package for fast review
- capture Andrew’s natural-language edits and approvals

**Proposed preview structure**
- Post ID
- Status
- Proposed type
- Proposed schedule
- Media preview(s)
- Caption
- Hashtags
- Location
- Notes/questions
- Suggested actions

**Natural-language examples to support**
- make this shorter
- swap the cover photo
- less poetic, more practical
- save this for next week
- approve the draft
- do not publish until I confirm

### 7. Approval Manager
**Responsibilities**
- enforce double approval
- preserve approval history
- prevent accidental publishing

**Approval stages**
1. **Draft approval**
   - confirms media set and content direction
   - allows scheduling / queue placement

2. **Publish approval**
   - explicit final authorization before live posting
   - must be recorded with timestamp and source message reference if possible

**Guardrails**
- no post enters live publish execution without publish approval
- if draft changes after draft approval, draft approval should be invalidated or re-confirmed
- if publish approval expires by policy, request a fresh one

### 8. Queue and Scheduler
**Responsibilities**
- hold approved content
- assign time slots
- request publish approval at the right time
- hand eligible posts to the publishing layer

**Scheduling behavior**
- support configurable preferred posting windows
- support daily/weekly cadence rules
- avoid clustering too many similar posts together
- adapt recommendations over time from engagement data

**Suggested initial scheduling model**
- queue stores proposed and final scheduled times separately
- scheduler marks posts as approaching publish window
- system notifies Andrew in Discord when publish approval is needed

### 9. Meta Auth Manager
**Responsibilities**
- manage Meta app credentials
- obtain and store tokens securely
- refresh/reacquire long-lived credentials as needed
- validate scopes and connected assets

**Expected official integration path**
- Instagram professional account connected to Facebook Page
- Meta developer app configured with the broader Meta/Facebook Graph path needed for Page-linked Instagram access
- OAuth/token flow resulting in usable access for publishing through the Facebook/Meta Graph route

**Validated setup finding**
- In Andrew's current Creator-account setup, the working auth/read path is the Facebook/Meta Graph path (`graph.facebook.com`) using Page-linked Instagram account access
- Attempting to use the Instagram-host token path (`graph.instagram.com`) produced `Invalid platform app`
- Post Relay should therefore treat the Facebook/Meta Graph route as the primary integration path for this setup unless later validation proves a different supported publish path is better

**Security design**
- store secrets outside source-controlled files where possible
- use environment variables or local secrets file excluded from version control
- log token events but never log raw secrets

### 10. Instagram Publisher
**Responsibilities**
- prepare publishable media payloads
- create media containers through the Graph API
- poll publish readiness if required by API behavior
- publish media once ready
- record remote ids and statuses

**Important note**
Meta’s capabilities and endpoints evolve. Final implementation should verify the current official support matrix for:
- single image publishing
- carousel publishing
- reels/video publishing
- metadata constraints
- page/account permission requirements

### 11. Publish Logger / Audit Store
**Responsibilities**
- record all key state transitions
- log API interactions at a safe summary level
- record approval history
- record final published asset ids and timestamps
- record failures with actionable error summaries

## Suggested Storage Model
For v1, a local file-based approach is likely sufficient and easier to inspect.

### Recommended storage layout
The original design expected local files. The current implementation uses SQLite as the durable workflow store plus generated artifact roots:
- `data/post_relay.sqlite` — default local SQLite database for indexed media, candidates, drafts, approvals, publish attempts, staged R2 records, post-publish snapshots, and insight snapshots
- configured processed Lightroom/year folders — immutable source of truth for source media
- configured review artifact root — thumbnails/contact sheets and local review packages
- configured publish export root — immutable-source Instagram-ready publish assets such as 4:5 feed exports
- configured R2 prefix — disposable temporary public staging objects for Meta-bound media URLs
- `.env` or local secret store — tokens/app secrets (not committed)

### Suggested post record fields
- id
- created_at
- updated_at
- source_files
- preview_files
- capture_dates
- inferred_trip
- inferred_location
- post_type
- caption_candidates
- selected_caption
- hashtag_candidates
- selected_hashtags
- location_text
- interview_context
- state
- schedule_proposed_at
- schedule_final_at
- draft_approval
- publish_approval
- publish_result
- engagement_metrics
- revision_history

## Suggested State Machine
Core states:
- ingesting
- needs_context
- drafting
- awaiting_review
- needs_edits
- approved_for_queue
- scheduled
- awaiting_publish_approval
- ready_to_publish
- posting
- posted
- failed
- archived

### Typical transitions
- ingesting -> drafting
- ingesting -> needs_context
- needs_context -> drafting
- drafting -> awaiting_review
- awaiting_review -> needs_edits
- needs_edits -> drafting
- awaiting_review -> approved_for_queue
- approved_for_queue -> scheduled
- scheduled -> awaiting_publish_approval
- awaiting_publish_approval -> ready_to_publish
- ready_to_publish -> posting
- posting -> posted
- posting -> failed

## Discord Review Flow Design
### Preview goals
- visually useful
- compact enough for chat
- easy to respond to in natural language

### Example preview payload structure
- **Post 014**
- Status: Awaiting review
- Type: Carousel
- Proposed slot: Tue 6:30 PM
- Files: 4 selected from Iceland set
- Location: Reykjavik, Iceland (?)
- Caption: [primary draft]
- Hashtags: [selected list]
- Notes: Need confirmation on exact neighborhood / whether to make it more personal

### Possible follow-up flows
- Andrew revises caption directly
- Andrew asks for alternate tones
- Andrew approves draft
- system stores approval and schedules it
- closer to publish time, system asks for final go-ahead

## Scheduling and Approval Strategy
Because Andrew chose double approval, scheduling should be designed around two checkpoints.

### Recommended implementation
1. Draft gets approved and enters queue
2. Scheduler assigns or confirms time slot
3. As publish window approaches, Discord message asks for final publish approval
4. Only after explicit approval does publisher execute

### Publish approval timing options
The implementation should allow later configuration of:
- exact-time approval required
- same-day approval window
- approval valid for a configurable number of hours before scheduled publish

For v1, simplest behavior:
- ask for final approval on the day of posting or shortly before scheduled time

## Recommendation Engine Design
Initial recommendation logic should be simple and interpretable.

### Inputs
- local `published_post_snapshots` containing final Meta-bound caption, media count/order, exported dimensions, timing, post type, and resolved location tag state
- local `media_insight_snapshots` containing read-only Meta metrics collected through explicit `analytics insights-fetch --execute`
- local `account_metric_snapshots` containing read-only creator-account follower/follows/media counts collected through explicit `analytics follower-fetch --execute`
- prior approval and revision patterns
- content category mix
- posting time history

### Early outputs
- advisory feedback summaries for individual published posts and recent-post sets
- local follower-growth summaries toward the 5,000 follower goal
- suggested post type and carousel count/order heuristics
- suggested posting window notes
- suggested caption tone/length notes
- warnings when evidence is weak or sample size is too small

### Later improvements
- learn best-performing formats by trip/theme
- learn Andrew’s stylistic preferences
- reduce interview frequency where prior signals are strong
- turn enough advisory feedback/follower-growth history into stronger deterministic recommendations without mutating post lifecycle state

## Error Handling
### Categories
- missing or unreadable media
- unsupported file format
- insufficient context for drafting
- ambiguous user instructions
- expired/invalid Meta token
- permission or scope mismatch
- API publish failure
- media processing failure

### Handling principles
- fail visibly, not silently
- keep partial work when possible
- surface actionable next steps in Discord
- never publish on uncertain state transitions

## Security Considerations
- do not store Meta secrets in tracked markdown/docs
- use environment variables or local ignored config files
- do not log raw access tokens
- restrict publishing to approved posts only
- preserve an audit trail of who approved what and when

## Proposed Implementation Phases

### Phase 1 — Local planning and review loop
Goal: prove the workflow without live publishing.

Includes:
- folder ingestion
- metadata extraction
- candidate building
- interviews for missing context
- caption/hashtag drafting
- structured Discord previews
- natural-language revision handling
- draft approval storage
- queue records

### Phase 2 — Scheduling and publish-approval loop
Goal: operationalize the queue safely.

Includes:
- schedule config
- queue manager
- publish-approval requests in Discord
- state transitions to ready_to_publish
- logging and audit improvements

### Phase 3 — Official Meta publishing integration
Goal: enable safe, real publishing.

Includes:
- Meta app integration
- token handling
- Instagram Graph API publishing
- error handling and retry logic
- post-publish notifications

Initial target assumptions for this phase:
- single-account v1
- target Instagram account is Andrew's `andrewhml`
- target account type is Creator
- architecture should remain extensible for future multi-account support without implementing full multi-tenant complexity in v1

### Phase 4 — Optimization and learning
Goal: improve performance and reduce manual friction.

Includes:
- engagement tracking
- recommendation tuning
- smarter schedule suggestions
- better post-type selection

## Technology Direction
Current implementation direction:

- **Runtime:** Python package under `src/post_relay/`
- **CLI:** Typer entry point `post-relay`
- **Storage:** local SQLite database, default `data/post_relay.sqlite`
- **Media processing:** Pillow-backed local artifact/export rendering where needed
- **Scheduling:** local CLI/state-machine preflight and explicit scheduled publish runner command
- **Discord communication:** private-DM-first commands with no-network apply harnesses and live-capable send/poll commands
- **Publishing:** official Meta Graph API client logic through `graph.facebook.com`

## Andrew Setup Checklist
This is the practical checklist for Andrew before live publishing integration.

### Account setup
- Convert Instagram account to a professional account if not already
- Current chosen target: Andrew's `andrewhml` Instagram account as a **Creator** account
- Create or identify a Facebook Page for Andrew's creator/travel identity and connect it to the Instagram account
- Keep this identity separate from Andrew's consulting business brand `Syntheus`
- Confirm the Instagram account is linked properly to that Facebook Page

### Meta developer setup
- Create a Meta developer account if needed
- Create a Meta app for this automation tool (current chosen app/project name: `Post Relay`)
- Add the relevant Instagram/Graph products required for publishing
- Configure OAuth/permissions as required by the official docs
- Add Andrew as admin/tester/developer roles where needed

### Permissions and review readiness
- Identify which permissions/scopes are required for:
  - reading connected Instagram account info
  - publishing content
  - managing media publishing workflow
- Confirm whether the app can remain in development mode for personal use or whether any review is needed for the final setup

### Token handling
- Generate a usable long-lived token according to the official flow
- Store app id, app secret, and access tokens securely
- Be ready to test token refresh or renewal behavior

### Asset verification
- Confirm test media can be hosted/readied in a form acceptable to the Graph API if direct local upload is not the publish path
- Confirm which content types are supported in the current official flow:
  - image posts
  - carousel posts
  - reels/video posts

### Final verification before build completion
- Verify the exact current Graph API docs for publishing support and limitations
- Run a controlled test publish to a non-critical/test setup if possible

## Questions to Verify During Implementation
These should be verified against the current official Meta docs at build time:
- exact supported account types for content publishing
- exact scopes/permissions required
- whether media must be available via publicly reachable URL or can be uploaded another way in the intended flow
- carousel creation requirements
- reels/video container requirements
- location/tag metadata limitations
- rate limits and publish quotas
- the exact publish/create flow on the Facebook/Meta Graph route for a Page-linked Creator account

## Recommended Next Artifacts
The canonical active roadmap is now `docs/plans/current-agent-roadmap.md`. After `feat/follower-growth-tracking` lands, choose the next detailed artifact from private-DM operating-loop improvements, proactive opportunity DM controls, video/reel validation, or deeper local media discovery/enrichment.

## Current Readiness Criteria
The system is ready for the next optimization milestone when:
- `feat/follower-growth-tracking` is merged and local `main` is synced
- `.venv/bin/python -m pytest -q` is green
- recommendation feedback and follower-growth summaries read only local snapshots and remain advisory-only
- any live insights collection remains explicitly gated by `analytics insights-fetch --execute`
- any live follower metrics collection remains explicitly gated by `analytics follower-fetch --execute`

## Summary
This design deliberately separates:
- planning and drafting
- review and approvals
- queueing and scheduling
- official publishing

That separation reduces risk, keeps the tool explainable, and makes it easier to build safely in stages.
