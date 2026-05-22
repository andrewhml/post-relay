# Post Relay

Local-first Instagram travel-photo workflow for turning processed photo folders into reviewed, scheduled, and optionally published posts.

Post Relay started as Andrew's personal workflow for the `andrewhml` Creator account, but the product direction is now to make it usable as a local-first app for other people too. Each user should bring their own photo folders, local database, private credentials, and optional integrations.

## Status

Post Relay is experimental and local-first. The current app supports:

- folder-based local media indexing with dimensions/orientation and available EXIF date/camera/lens metadata
- SQLite-backed candidates, posts, approvals, schedules, analytics snapshots, opportunity records, and active user/agent goal artifacts
- staged local review artifacts: Stage 1 selection, Stage 2 crop/framing, Stage 3 final preview
- explicit media selection, ordering, lead image, crop/center feedback, and approval invalidation on material edits
- hook/caption/metadata package planning and acceptance
- dry-run Discord-style preview and private-DM operating-loop planning
- optional live-capable Discord DM commands behind environment-provided bot credentials
- guarded Cloudflare R2 staging upload/cleanup for selected publish media
- official Meta/Facebook Graph read-only validation and guarded single-image/carousel publish validation
- final Meta-bound publish previews, schedule enforcement, durable final publish approvals, and scriptless unattended publish planning
- local post-publish snapshots, read-only insights collection behind explicit `--execute`, follower summaries, and advisory feedback summaries

Safe defaults matter: local preview workflows make no network calls, source media is not mutated, and live publishing requires explicit approval and execute flags.

## Onboarding modes

Start with the lightest mode that gives you value.

| Mode | Purpose | External accounts required? |
| --- | --- | --- |
| Local preview | Scan local processed folders, build candidate posts, render contact sheets, plan copy | No |
| Connected Meta tester | Validate your own Facebook Page + professional Instagram account through the official Graph path | Yes |
| Self-managed R2 staging | Stage selected publish assets to your own public HTTPS bucket for Meta publishing | Optional |
| Managed staging | Future beta path where selected media can be staged without each user creating R2 credentials | Paused |

For the full setup guide, see `docs/setup-own-instance.md`.

For the reusable-user product roadmap, see `docs/plans/product-onboarding-roadmap.md`.

## Quickstart: local preview only

This path does not require Meta, Discord, R2, or any network calls.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/post-relay setup
```

The setup wizard prompts for a processed/exported photo folder, copies `.env.example` and `config/photo_sources.example.yaml` only when the private files are missing, writes your first local photo source, creates local artifact/export directories, initializes the SQLite DB, and makes no network calls. It now also prints a goal-setup command so a user and agent can agree on the north star before the first chat-driven post recommendation.

You can also pass the folder directly:

```bash
.venv/bin/post-relay setup --photo-root /path/to/your/processed/photos
```

Then run:

```bash
.venv/bin/post-relay doctor --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env
.venv/bin/post-relay index scan --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay library stats --db data/post_relay.sqlite
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --post-id 1 --stage select --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --post-id 1 --db data/post_relay.sqlite
```

Generated review artifacts are written under the configured artifact root, usually `data/review_artifacts/`. Source media stays untouched.

## Local files

These files are intentionally local/private and should not be committed:

- `.env` — private credentials, tokens, and per-instance IDs
- `config/photo_sources.yaml` — local/NAS paths and optional staging config
- `data/post_relay.sqlite` — local SQLite database
- `data/review_artifacts/` — generated contact sheets/thumbnails
- `data/publish_exports/` — generated publish-ready media files

Use these committed templates instead:

- `.env.example`
- `config/photo_sources.example.yaml`

## Optional Meta/Instagram integration

Meta integration is optional. Use it only after the local workflow is useful.

Requirements:

- Instagram professional Creator or Business account
- linked Facebook Page
- Facebook user with access to that Page
- Meta app credentials or tester access to a shared Post Relay app
- private user access token with the required Page/Instagram permissions

Configure your own values in `.env`; do not reuse Andrew's IDs or tokens.

Trusted-tester OAuth helper, account discovery, and validation:

```bash
.venv/bin/post-relay meta oauth-login --env-file .env
.venv/bin/post-relay meta oauth-login --env-file .env --execute --code OAUTH_CODE_FROM_REDIRECT
.venv/bin/post-relay meta oauth-login --env-file .env --execute --code OAUTH_CODE_FROM_REDIRECT --update-env --page-id YOUR_FACEBOOK_PAGE_ID --instagram-account-id YOUR_INSTAGRAM_ACCOUNT_ID
.venv/bin/post-relay meta discover-accounts --env-file .env --dry-run
.venv/bin/post-relay meta discover-accounts --env-file .env --execute
.venv/bin/post-relay meta discover-accounts --env-file .env --execute --update-env --page-id YOUR_FACEBOOK_PAGE_ID --instagram-account-id YOUR_INSTAGRAM_ACCOUNT_ID
.venv/bin/post-relay meta validate-readonly --env-file .env --dry-run
```

Token extension dry-run and execute path:

```bash
.venv/bin/post-relay meta token-extend --env-file .env
.venv/bin/post-relay meta token-extend --env-file .env --execute --update-env
```

Publishing is guarded and uses official Meta/Facebook Graph routes only. Public HTTPS media URLs are required for Meta publish containers; local file paths are not sent directly to Meta.

## Recommendation-engine direction

Post Relay's next product direction is making the agent smarter rather than adding more staging infrastructure. See `docs/plans/recommendation-engine-roadmap.md` for the current planning baseline. Recommendation work should start from the active local user/agent goal artifact plus auditable signals already present in the system: candidate metadata, folder/year/filename descriptors, selected media order, crop/export readiness, approvals and revisions, scheduled/published payloads, stored read-only insights, and follower-growth summaries.

The local signal baseline command summarizes which recommendation inputs are present, sparse, or missing without making network calls or mutating state. The candidate ranking command then scores candidate groups with deterministic local signals and explains every contribution without creating or changing posts. Context question generation reuses explicit draft content plus folder/year descriptors before asking only targeted remaining gaps, such as an accepted freeform location that still needs an optional reviewed Meta Page tag. Schedule-window suggestions surface the existing scheduled queue before recommending another slot. Caption-style recommendations read accepted guided packages, active approvals, published snapshots, and stored insight snapshots to advise direction without rewriting saved copy:

```bash
.venv/bin/post-relay recommendations signals --db data/post_relay.sqlite
.venv/bin/post-relay recommendations candidates --limit 5 --db data/post_relay.sqlite
.venv/bin/post-relay recommendations schedule --limit 3 --db data/post_relay.sqlite
.venv/bin/post-relay recommendations caption-style --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions generate --post-id 1 --db data/post_relay.sqlite
```

The active goal artifact gives the agent a durable north star for proactive suggestions and question reduction:

```bash
.venv/bin/post-relay goals init --db data/post_relay.sqlite \
  --title "Travel account north star" \
  --statement "Grow with saveable city-guide carousels." \
  --target-audience "Travelers planning city walks." \
  --pillar "city guides" \
  --pillar "photo essays" \
  --cadence "2-3 posts per week" \
  --metric "saves" \
  --metric "shares" \
  --strategy-note "Recommend one best next post with rationale." \
  --constraint "avoid places not pictured" \
  --reviewed-by YOUR_NAME
.venv/bin/post-relay goals show --db data/post_relay.sqlite
.venv/bin/post-relay goals agent-brief --db data/post_relay.sqlite
```

Early recommendation milestones should stay advisory and deterministic: rank candidate groups, explain why a set is promising, suggest post type/caption angle/schedule windows, and reduce unnecessary context questions by reusing the active goal and prior accepted context. They should not mutate posts, approvals, schedules, Discord state, R2 staging, or Meta state; read-only Meta collection remains behind explicit analytics `--execute` commands and recommendation commands should consume stored local snapshots by default. Schedule recommendations must show already scheduled posts before proposing a new slot and must not schedule automatically.

## Optional R2 staging

R2 staging is optional and exists to provide public HTTPS media URLs for selected publish assets. For the first friend/beta round, users should bring their own Cloudflare R2 bucket; see `docs/byo-r2-bucket-setup.md` for the exact Cloudflare UI path and Post Relay config.

The current implementation supports self-managed R2 credentials. Managed staging for friends/beta users is designed in `docs/plans/managed-r2-staging-design.md`, but that direction is paused for now while Post Relay focuses on smarter agent behavior and recommendation-engine foundations. Do not revive managed staging unless Andrew explicitly reactivates it; it must still avoid exposing raw shared R2 credentials to users.

Configure non-secret bucket settings in `config/photo_sources.yaml` and secrets in `.env`:

```bash
POST_RELAY_R2_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
POST_RELAY_R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
POST_RELAY_R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
```

Plan before upload:

```bash
.venv/bin/post-relay doctor --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env
.venv/bin/post-relay drafts r2-stage-plan --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

With `r2_staging.enabled`, `post-relay doctor` now performs a no-network R2 readiness check: bucket, S3 endpoint URL, public base URL, required env values, and the common mistake of using the S3 API endpoint as the public object URL base.

Execute only after inspecting the dry-run output:

```bash
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute
```

Cleanup is recorded-object scoped:

```bash
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute --reason "publish complete"
```

## Optional Discord workflow

The local DM harness can be used without live Discord:

```bash
.venv/bin/post-relay dm intake --message "start a post about Kyoto night market" --discord-channel-id local-test --db data/post_relay.sqlite
.venv/bin/post-relay dm next-action --discord-channel-id local-test --db data/post_relay.sqlite
```

Live Discord DM sends require a private bot token and explicit live-capable commands. Keep bot credentials in `.env`. If `dm next-action` is started before any active goal exists, it returns a local `goal_onboarding` prompt that asks the user to fill in the goal statement, audience, content pillars, cadence, success metrics, strategy notes, and constraints before the agent recommends a first post.

## Review and publish workflow

Common local commands:

```bash
.venv/bin/post-relay drafts media-edit --post-id 1 --lead 3 --keep 1,3,5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --post-id 1 --stage crop --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts crop-feedback --post-id 1 --shift 3:B2 --center 5 --tighten 6 --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-plan --post-id 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts guided-package-accept --post-id 1 --caption-index 1 --location "Seoul, South Korea" --story-angle "night market alleys" --mood cinematic --audience-hook "food and light" --db data/post_relay.sqlite
.venv/bin/post-relay drafts location-candidates --post-id 1 --query "Seoul South Korea" --db data/post_relay.sqlite --env-file .env
.venv/bin/post-relay drafts location-tag-set --post-id 1 --page-id FACEBOOK_PAGE_ID --name "Seoul, Korea" --db data/post_relay.sqlite
# Or explicitly bypass the Instagram location tag when you intend to publish without one:
.venv/bin/post-relay drafts location-tag-skip --post-id 1 --reason "No reliable Meta Page match" --db data/post_relay.sqlite
.venv/bin/post-relay drafts final-preview-artifact render --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts publish-exports render --post-id 1 --profile feed_portrait_3x4 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts submit --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --post-id 1 --approved-by YOUR_NAME --notes "Content approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts schedule --post-id 1 --scheduled-for "2026-05-05T09:30:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve-publish --post-id 1 --approved-by YOUR_NAME --notes "Final approval" --db data/post_relay.sqlite
```

Final publish preview and scheduled publish preflight from staged R2 media:

```bash
.venv/bin/post-relay meta final-publish-preview --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay meta publish-scheduled --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

Execute live Meta publish only when due and explicitly authorized:

```bash
.venv/bin/post-relay meta publish-scheduled --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env --execute
```

## Safety model

- Never commit secrets or tokens.
- Never paste tokens into chat, logs, docs, tests, or PRs.
- Keep source media immutable.
- Default to local/no-network/dry-run commands where available.
- Use official Meta/Facebook Graph routes only for Instagram publishing.
- Do not use browser automation, password scraping, or unofficial posting methods.
- Require content approval before final publish approval.
- Invalidate approvals after material edits.
- Create Meta containers only from guarded execute paths.
- Treat freeform location text, alt text, rationale, collaborators, music, and story/reel-only metadata as local/review-only unless a later milestone validates official support.
- If a post has freeform location context, choose a reviewed Meta/Facebook Page `location_id` with `drafts location-tag-set` or explicitly bypass it with `drafts location-tag-skip`; Post Relay will warn in final previews and scheduled publish plans when no publishable location tag will be sent.

## Development

Run tests with:

```bash
.venv/bin/python -m pytest -q
```

Future agents should read `AGENTS.md` and `docs/plans/current-agent-roadmap.md` before changing product behavior. Andrew-specific instance facts and live-operation handoff details belong in agent/operations docs, not in generic onboarding instructions.
