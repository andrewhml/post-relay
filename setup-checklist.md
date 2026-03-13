# Instagram Travel Content Tool — Andrew Setup Checklist

## Status
Draft v0.1

## Purpose
This checklist is the practical setup guide for Andrew so **Post Relay** can use the clean, official Meta/Instagram publishing path.

This is intentionally written as an action list, not a design doc.

## Outcome We Want
By the end of this checklist, Andrew should have:
- an Instagram account configured for official publishing support
- the account connected to the correct Facebook Page
- a Meta developer app created
- the relevant products/permissions configured
- credentials and tokens ready for local secure use
- enough setup completed to test publishing safely

## Before You Start
Have these ready:
- access to the Instagram account you want to publish to
- access to the Facebook account that will manage the connected Page
- access to Meta for Developers
- a note-taking spot for app IDs, page IDs, account IDs, and setup status

## Phase 1 — Instagram and Facebook Foundation

### 1. Confirm Instagram account type
- Check whether the Instagram account is currently:
  - Personal
  - Creator
  - Business

### 2. Convert to a professional account if needed
For the clean publishing flow, the account should be a professional account.

**Current decision:**
- Use Andrew's `andrewhml` account as a **Creator** account for this workflow.
- Keep this separate from the `Syntheus` consulting/business identity.

### 3. Create or identify the Facebook Page
- Create a Facebook Page if you do not already have one for this Instagram presence
- If you already have a Page, verify you still control it
- Make sure this Page is the one you want associated with the Instagram account

### 4. Link Instagram to the Facebook Page
- Connect the Instagram professional account to the Facebook Page
- Verify the connection from both sides if Meta’s UI exposes it in more than one place
- Confirm the correct Instagram account is linked, not an old or alternate one

### 5. Confirm account admin/control access
Make sure the Facebook account you will use for setup has sufficient access to:
- the Instagram account
- the Facebook Page
- the Meta app you will create

## Phase 2 — Meta Developer Setup

### 6. Create or confirm your Meta developer account
- Sign in to Meta for Developers
- Complete any developer registration steps if prompted

### 7. Create a Meta app for this tool
Create a dedicated app for the Instagram publishing workflow.

Chosen naming:
- Meta app / project name: `Post Relay`

### 8. Record key app details
Capture these values in your secure notes:
- App name
- App ID
- App secret location (do not paste it into normal chat)
- App mode/status (development/live)

### 9. Add the relevant Meta products
Inside the app, add the Instagram/Graph-related products needed for publishing.

At minimum, we expect the app to need the official Instagram publishing-related capabilities under Meta’s current platform model.

### 10. Add yourself in any needed app roles
If Meta requires roles for testing in development mode, add the right Facebook/Instagram-connected users as:
- admin
- developer
- tester
- or equivalent roles required by the current platform UI

## Phase 3 — Permissions and Access

### 11. Identify required permissions/scopes
During setup, note which permissions/scopes Meta currently requires for:
- reading connected Instagram account information
- managing/publishing Instagram content
- reading Page/account linkage needed for the workflow

### 12. Determine whether app review is needed
Check whether your intended personal-use workflow can remain in:
- development mode
nor whether any permissions require:
- app review
- advanced access
- business verification

If review is needed, note that early so we can plan around it.

### 13. Confirm business verification requirements
Some Meta flows/features may require business verification or related account trust steps.

Check whether your app or intended permissions trigger any of the following:
- business verification
- identity confirmation
- additional platform compliance steps

## Phase 4 — Authentication and Tokens

### 14. Configure the login/auth flow needed for the app
- Set up the official auth flow required by the current Meta docs
- Record any redirect URIs we need later for local tooling
- Keep a secure note of what auth method was chosen

### 15. Generate an access token through the proper flow
Obtain the token in the official way required for the app and account type.

Goal:
- produce a token suitable for testing the Instagram publishing workflow

### 16. Confirm long-lived token support
- Check whether the token can be exchanged/extended into a long-lived token
- Record expected expiration behavior
- Record what refresh/replacement process Meta currently requires

### 17. Store credentials securely
Prepare secure local storage for:
- app id
- app secret
- access token
- any refresh/extension details

**Do not store secrets in:**
- public notes
- tracked markdown files
- Discord messages
- screenshots shared casually

## Phase 5 — Asset and Publishing Readiness

### 18. Confirm supported publish types in the current docs/UI
Verify the current official support for the exact content we want to use:
- single image posts
- carousel posts
- reels / video publishing

Record anything surprising or limited.

### 19. Confirm media delivery expectations
We need to verify how the Graph API expects media to be made available for publishing.

Questions to answer during setup/validation:
- Does the API expect publicly reachable media URLs?
- Is there an official upload path we should use?
- Are there different rules for images vs reels/videos?

### 20. Confirm metadata limitations
Check what metadata the current publishing path supports or does not support, including things like:
- caption
- hashtags in caption
- location behavior
- collaborator tags
- alt text or accessibility-related fields if available

### 21. Prepare a test media set
Create a small local test set containing:
- 1 strong single image
- 1 small carousel candidate
- 1 short video/reel candidate

This will let us validate the workflow safely before touching larger batches.

## Phase 6 — Validation

### 22. Validate account linkage programmatically or in Meta tools
Before we build too far, we should be able to confirm:
- the app can see the expected connected assets
- the Instagram account/page linkage is correct
- permissions are sufficient for the intended operations

### 23. Run a controlled publishing test when ready
Once the app, account, and token path are stable, run a controlled test using non-critical media.

Preferably:
- test on a safe post you do not mind publishing
- or use the least risky publish path first

### 24. Record all IDs we will need later
Keep a secure setup note with these values if available:
- App ID
- Facebook Page ID
- Instagram Business/Professional Account ID
- any relevant business/account identifiers
- token expiration date/time

## What to Send Me Back Once You’ve Started
When you’ve worked through the checklist, the most useful status update back to me is:

- Instagram account type: `Business / Creator / still personal`
- Facebook Page linked: `yes/no`
- Meta app created: `yes/no`
- App mode: `development/live`
- Required permissions identified: `yes/no/partial`
- Token acquired: `yes/no`
- Long-lived token acquired: `yes/no`
- Single image support confirmed: `yes/no`
- Carousel support confirmed: `yes/no`
- Reels support confirmed: `yes/no`
- Anything Meta blocked/confused: short notes

## Expected Friction Points
The most likely setup snags are:
- wrong Instagram account type
- incomplete Facebook Page linkage
- confusing Meta permission naming
- development vs live mode limitations
- token generation/extension confusion
- unclear support differences between image/carousel/reels

If you hit one of those, send me the exact blocker and I’ll help untangle it.

## Validated Setup Findings So Far
Andrew's current setup has already validated several important pieces:
- `andrewhml` is connected as the linked Instagram account
- the `Andrewhml` Facebook Page is visible to the app once the correct use case and Facebook-side permissions are enabled
- Page lookup and linked Instagram-account discovery work through `graph.facebook.com`
- Instagram account reads and media reads work through the Facebook/Meta Graph route
- attempting the Instagram-host token route (`graph.instagram.com`) returned `Invalid platform app`

Practical implication:
- Post Relay should proceed assuming the Facebook/Meta Graph route is the correct primary integration path for this Creator-account setup

## Important Note on Documentation Verification
I attempted to fetch Meta’s official docs directly into the workspace, but Meta’s site did not return usable content through the fetch path available here.

So this checklist is based on:
- the official Meta platform direction for Instagram Graph publishing
- current platform expectations at a high level
- the design constraints already captured in our docs
- the validated behavior observed in Andrew's live setup

Before final implementation, I still want to do a targeted verification of the exact current Meta requirements for:
- permissions/scopes
- publish path mechanics
- supported content types
- token behavior

## Suggested Next Step After This Checklist
Once you start working through this, I should prepare one of these next:
- `implementation-plan.md`
- `data-model.md`
- `meta-api-notes.md`

Recommended next doc: **implementation plan**.
