# Instagram Travel Content Tool — Requirements

## Status
Draft v0.1

## Purpose
Build **Post Relay**, a tool that helps Andrew work through a multi-year backlog of travel content and turn it into high-quality Instagram posts that can grow followers over time without sacrificing quality or control.

The system should support planning, drafting, discussion, approval, scheduling, and publishing, while keeping Andrew in the loop before anything goes live.

## Primary Goal
Create a reliable workflow for turning local travel photos and videos into Instagram-ready posts with:
- strong captions
- useful metadata
- thoughtful scheduling
- Discord-based review
- explicit human approval before publishing

## Product Principles
- Human-in-the-loop by default
- Quality over volume
- Official/supported publishing path preferred
- Draft first, publish later
- Ask focused questions when context is missing
- Learn over time from engagement and feedback
- Keep the Discord review flow rich and structured, but not heavy

## Current Product Decisions
- Product / app name: **Post Relay**
- Initial target Instagram account: Andrew's `andrewhml`
- Initial target account type: **Creator**
- Brand context: Andrew's creator/travel photography identity
- Separate business identity: `Syntheus`
- Initial implementation scope: **single-account v1** with future room for multi-account support

## Source Media Assumptions
### Input source
- Local folders on Andrew's machine
- Media may originate from a NAS, then be brought local for processing

### Expected media characteristics
- Processed photos
- Shot on Sony A7IV
- Mix of portrait and landscape
- Some metadata available
- GPS/location metadata generally unavailable

## Supported Content Types
The system should support:
- Single-image posts
- Multi-image carousel posts
- Reels / short-form video experiments

## Core Workflow
### 1. Ingest content
The system should:
- read local folders containing candidate travel media
- inspect available file metadata
- group related files when appropriate
- identify candidate posts from one or more assets

### 2. Determine confidence
Before drafting, the system should evaluate whether it has enough information to create a strong post.

It should use:
- file metadata
- folder structure
- filenames
- nearby/related assets
- prior user guidance
- previous interview answers

### 3. Interview when context is insufficient
If the system cannot confidently produce a strong draft, it should ask Andrew focused follow-up questions in Discord.

The system should ask only the minimum necessary questions.

#### Examples of factual questions
- Where was this taken?
- What trip was this from?
- Rough date or season?
- Who was there?

#### Examples of creative questions
- What vibe do you want here?
- Should this feel personal, cinematic, funny, informative, or aspirational?
- Is there a story behind this shot?
- Anything you want included or avoided?

#### Interview rules
- Prefer lightweight interviews first
- Use deeper interviews only when needed for a better post
- Never fabricate factual details like location or event specifics
- Store useful answers as reusable context for later drafts

### 4. Draft post package
For each candidate post, the system should prepare a draft package containing:
- selected media
- suggested post type (single image, carousel, reel)
- draft caption
- suggested hashtags
- suggested location if known or inferred with user confirmation
- optional alt text / accessibility notes if useful
- optional rationale for why the post may perform well
- recommended posting time / schedule slot

### 5. Send draft preview in Discord
The system should send rich, structured previews in Discord.

The preview should be:
- easy to scan
- not too heavy
- visually useful for approval

#### Preview expectations
- Show the actual image previews where possible
- Include the proposed caption
- Include hashtags
- Include suggested location
- Include proposed post type
- Include proposed schedule
- Include current state/status
- Include any open questions or confidence gaps

### 6. Discussion and revision
Andrew and the system should be able to discuss the draft in natural language.

Examples:
- make this funnier
- swap image 2 for image 4
- make the caption less dramatic
- save this for summer
- turn this into a carousel
- give me three caption options

If needed, the system may use a confirmation step to ensure it correctly understood Andrew's intent.

### 7. Double approval
The workflow should use double approval.

#### Approval stage A: Draft approval
Andrew approves the content package itself:
- selected media
- caption direction
- hashtags / metadata
- overall post concept

Once approved, the draft may move to queueing/scheduling.

#### Approval stage B: Publish approval
Before the post actually goes live, Andrew gives final approval to publish.

This protects against mistakes and gives Andrew a final checkpoint.

### 8. Queueing and scheduling
The system should support building a backlog of approved posts for later dissemination.

Scheduling should:
- support daily posting plans
- allow schedule adjustment over time to optimize engagement
- support experimentation with timing and format
- avoid dumping large amounts of old travel content at once

The schedule logic should be adaptable as performance data accumulates.

### 9. Publish
Once final approval is given, the system should publish via the official/supported Instagram publishing path wherever possible.

Publishing should:
- log success/failure
- preserve auditability
- avoid posting without explicit publish approval

### 10. Notify and log
After publishing, the system should:
- notify Andrew in Discord
- log what was posted
- log when it was posted
- log which assets and caption version were used
- record any API or publishing errors

## Discord Interaction Requirements
### Preview style
Discord previews should be rich and structured.

They should include enough information to make a decision quickly without turning into a wall of text.

### Approval style
Interaction should be natural language first.

Examples:
- approve this draft
- queue this for next week
- publish this tomorrow if I confirm
- revise the hashtags
- give me a more personal caption

If intent is ambiguous, the system should ask for confirmation.

## Data / Metadata Requirements
For each post draft, the system should be able to store:
- unique post id
- source files
- trip/group identifier if known
- capture date if known
- estimated location if known
- interview answers / supporting notes
- post type
- caption versions
- hashtag versions
- schedule proposal
- current state
- approval history
- publish history
- engagement results when available

## State Model
Suggested states:
- ingesting
- needs_context
- drafting
- awaiting_review
- needs_edits
- approved_for_queue
- scheduled
- awaiting_publish_approval
- posted
- failed
- archived

## Recommendation / Adaptation Requirements
The system should recommend:
- best post format for a given media set
- likely good posting windows
- caption styles to test
- content mix over time

Over time, it should adapt based on:
- Andrew's feedback
- approval/revision patterns
- performance/engagement data

The system should become better at:
- choosing single image vs carousel vs reel
- picking stronger lead images
- drafting captions in Andrew's preferred style
- reducing unnecessary interview questions
- suggesting better timing

## Factual vs Creative Defaults
Default behavior:
- infer factual context when reasonably supported by files or prior user-provided context
- ask when confidence is low
- infer creative direction when possible
- allow Andrew to adjust either factual or creative assumptions at any time
- never invent uncertain real-world facts as if known

## Safety / Control Requirements
- No publishing without explicit publish approval
- No silent changes to approved drafts without informing Andrew
- No fabricated locations or facts
- Prefer official API/integration paths over brittle automation
- Preserve logs for audit and debugging

## v1 Scope Recommendation
Recommended v1 scope:
- local folder ingestion
- single-image and carousel drafting
- reel planning support
- reel publishing support only if the official path is stable for Andrew's account setup
- caption generation
- hashtag suggestion
- location suggestion / confirmation
- Discord preview workflow
- interview flow for missing context
- revision workflow
- double approval workflow
- queueing and scheduling
- publishing logs

## Out of Scope for Initial Version
Unless explicitly added later:
- autonomous posting without approval
- sketchy engagement automation
- fake comments/follows/DM growth tactics
- broad cloud-source integrations as a first step
- advanced analytics dashboards before core workflow works

## Open Questions
These still need decisions later:
- exact Instagram account type and Meta setup
- exact preview formatting in Discord
- exact schedule defaults before optimization begins
- whether publish approval happens immediately before scheduled time or within a configurable approval window
- how engagement data will be collected and analyzed
- whether there should be a lightweight web dashboard later

## Initial Success Criteria
The tool is successful if it can:
1. Take local travel media from a folder
2. Build a strong draft post package
3. Ask smart follow-up questions when needed
4. Send a rich preview to Discord
5. Support revision in natural language
6. Queue approved content
7. Require final approval before posting
8. Publish successfully and log the result

## Future Ideas
Potential later additions:
- trip-level campaign planning
- seasonal resurfacing suggestions
- automatic duplicate/similarity detection
- engagement-based content strategy tuning
- better reel assembly suggestions
- web dashboard for queue management
- A/B testing caption styles
