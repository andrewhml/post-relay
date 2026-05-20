# Post Relay Reusable-User Onboarding Roadmap

> **For Hermes:** Use one rollback-safe branch and PR per milestone. Keep the app local-first, dry-run-first, and source-media immutable while lowering setup burden in layers.

**Goal:** Move Post Relay from Andrew's local tool toward a reusable local-first app that friends can try with their own photo libraries, then optionally connect their own Instagram accounts and managed media staging.

**Architecture:** Each user runs a local Post Relay instance with their own source photo folders, SQLite database, review artifacts, approvals, and private credentials. Shared services should be optional and additive: a Meta app for tester OAuth, then a managed staging broker for public HTTPS media URLs. No milestone should require uploading an entire source library or sharing Andrew's personal tokens, Page IDs, Instagram account ID, Discord bot token, or raw R2 credentials.

**Tech Stack:** Python 3.9+, Typer CLI, SQLite, local YAML config, private `.env`, official Meta/Facebook Graph APIs, optional Cloudflare R2 staging.

---

## Product principle

Start with a heavier local setup that works today, then progressively remove the highest-friction setup steps if people like the workflow.

The onboarding ladder is:

1. Local preview mode: no accounts, no uploads, no network.
2. Connected Meta tester mode: users authenticate their own Page-linked Instagram professional account through the Post Relay Meta app while tokens stay local.
3. Managed staging mode: selected publish media can be staged through a managed R2 path without users creating Cloudflare accounts or receiving raw bucket credentials.
4. Guided beta mode: setup, diagnostics, account discovery, and staging become guided CLI flows.

## Safety and ownership rules

- Source photo folders remain local and immutable.
- Local SQLite databases and review artifacts are per-user and not shared.
- `.env` files are private and never committed.
- Andrew's instance IDs are not defaults for other users.
- Users must authenticate their own Facebook user, Facebook Page, and Instagram professional account for publishing.
- Managed staging, when added, uploads only explicitly selected publish media, not whole libraries.
- Managed staging must use per-user prefixes, randomized object keys, TTL cleanup, quotas, and delete controls.
- Raw R2 S3 credentials should not be shared with testers; prefer a broker or presigned-upload flow.
- Live Meta publishing remains official-API-only and gated by content approval, publish approval, schedule checks, and explicit execute mode.

## Milestone 1: `docs/friend-onboarding-setup`

**Goal:** Make the current local-first setup understandable for someone who is not Andrew.

**Scope:**
- Rewrite `README.md` around reusable local-only onboarding first.
- Add `docs/setup-own-instance.md` as the detailed friend/beta setup guide.
- Generalize `.env.example` so it contains placeholders and grouped optional integration sections.
- Generalize `config/photo_sources.example.yaml` so it does not default to Andrew's local paths or R2 bucket.
- Move Andrew-specific setup facts out of README-style public onboarding surfaces and keep them in agent/operations handoff docs only.
- Update `docs/plans/current-agent-roadmap.md`, `implementation-plan.md`, and `AGENTS.md` so future agents see reusable-user onboarding as the current product direction.

**Verification:**

```bash
.venv/bin/python -m pytest -q
```

**Out of scope:**
- No code behavior changes.
- No OAuth flow.
- No managed R2 staging service.
- No live Discord, R2, or Meta calls.

## Milestone 2: `feat/setup-doctor` (in progress)

**Goal:** Replace manual setup debugging with a no-network diagnostic command.

**Behavior:**
- Add `post-relay doctor --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env`.
- Report whether config files exist, DB exists, photo roots are readable, artifact/export roots are writable, optional Meta variables are present, optional Discord variables are present, and R2 is enabled/configured.
- Redact all secret-like values.
- Make no network calls by default.
- Return actionable next commands.

**Safety:** Diagnostics must not print tokens, mutate posts, upload media, call Discord, call R2, call Meta, or publish.

## Milestone 3: `feat/setup-wizard`

**Goal:** Make the local-only trial path one command plus prompts.

**Behavior:**
- Add `post-relay setup` to copy `.env.example` and `config/photo_sources.example.yaml` when missing.
- Prompt for at least one processed photo folder path.
- Create local data directories.
- Initialize the SQLite database.
- Optionally run the first no-network scan after confirmation.
- End with the next local commands for candidates and artifacts.

**Safety:** Non-destructive; never overwrite existing `.env`, `config/photo_sources.yaml`, or SQLite DB without explicit confirmation.

## Milestone 4: `feat/meta-account-discovery`

**Goal:** Reduce Meta setup friction before full OAuth by discovering account IDs from an existing private token.

**Behavior:**
- Add `post-relay meta discover-accounts --env-file .env`.
- Load an existing `POST_RELAY_USER_ACCESS_TOKEN` privately.
- Call read-only Graph routes to list visible Facebook Pages and linked Instagram professional accounts.
- Let the user choose a Page/IG pair and update only non-secret account ID fields in `.env` after confirmation.
- Keep sanitized output and no token logging.

**Safety:** Read-only Meta calls only; no publishing endpoints.

## Milestone 5: `feat/meta-oauth-login`

**Goal:** Let trusted beta users authenticate their own account through the Post Relay Meta app instead of using Graph API Explorer.

**Behavior:**
- Add `post-relay meta login --env-file .env`.
- Open a Meta OAuth URL for the configured app.
- Receive a local callback or documented hosted callback.
- Exchange authorization code for a user token and extend it when supported.
- Discover visible Pages and linked Instagram accounts.
- Save the selected token/page/IG IDs to the private `.env` only after confirmation.
- Run sanitized read-only validation.

**Prerequisites:** Users are added as app testers or the app has the required reviewed permissions for broader distribution.

**Safety:** Tokens stay local; output redacts secrets; no publishing endpoints.

## Milestone 6: `docs/managed-staging-design`

**Goal:** Design shared R2 staging before implementation.

**Design topics:**
- User identity and auth for the staging service.
- Per-user/post object key format.
- Randomized/sanitized keys.
- Upload authorization model: brokered upload or presigned URLs.
- Public URL generation for Meta Graph.
- TTL policy for immediate and scheduled posts.
- Quotas, max media size, cleanup, delete-after-publish.
- Privacy copy for users.
- Local DB records for managed staged media.
- Failure modes and rollback.

## Milestone 7: `feat/managed-r2-staging-mvp`

**Goal:** Let beta users stage only selected publish media without configuring their own R2 bucket.

**Behavior:**
- Add managed staging config separate from local self-managed R2 config.
- Upload selected included post media only.
- Persist staged public URLs and expiry metadata locally.
- Prefer exported publish assets when present.
- Add cleanup/delete command for staged objects.
- Keep dry-run planning as the default.

**Safety:** Do not expose raw R2 credentials to users. Do not upload source folders or review artifacts by default. Do not publish.

## Milestone 8: `feat/onboarding-status`

**Goal:** Give beta users a simple readiness summary.

**Behavior:**
- Add `post-relay onboarding-status` or extend `doctor` to summarize:
  - Local preview ready.
  - Meta connected.
  - Staging ready.
  - Ready-to-publish blockers for a chosen post.
- Print the next safest command for each incomplete layer.

## Later direction

Only after local setup, Meta auth, and managed staging are proven with trusted testers should Post Relay consider hosted state, a web UI, app review for broader Meta distribution, or multi-tenant server-side workflows. Until then, keep the product local-first and make each optional integration layer valuable on its own.
