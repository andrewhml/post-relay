# Set up your own Post Relay instance

Post Relay is currently a local-first app. Each user should run their own local instance with their own photo folders, SQLite database, review artifacts, and private credentials.

You do not need Meta, Discord, or R2 to try the core workflow. Start local-only, then connect optional integrations after the local review loop feels useful.

## 1. Local-only quickstart

From the repo root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/post-relay setup
```

The setup wizard prompts for a processed/exported photo folder. It copies `.env.example` and `config/photo_sources.example.yaml` only when the private files are missing, writes your first local photo source, creates local artifact/export directories, initializes the SQLite DB, and makes no network calls.

You can also pass the folder directly:

```bash
.venv/bin/post-relay setup --photo-root /path/to/your/processed/photos
```

Run the setup doctor before the first scan. It checks local files, readable photo roots, writable artifact/export roots, and optional integration env vars without making network calls or printing secrets:

```bash
.venv/bin/post-relay doctor --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env
```

Then initialize and scan:

```bash
.venv/bin/post-relay db init --db data/post_relay.sqlite
.venv/bin/post-relay index scan --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay library stats --db data/post_relay.sqlite
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
```

Create and review a first post:

```bash
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --post-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --post-id 1 --stage select --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --post-id 1 --db data/post_relay.sqlite
```

This mode makes no Meta, Discord, or R2 calls. Source media is read but not moved, deleted, or modified.

## 2. Local files and what to customize

Private/local files:

- `.env`: private credentials and account IDs. Never commit this.
- `config/photo_sources.yaml`: local/NAS photo paths, artifact roots, and optional R2 bucket settings. Never commit this.
- `data/post_relay.sqlite`: your local database.
- `data/review_artifacts/`: generated local review sheets and thumbnails.
- `data/publish_exports/`: generated publish-ready export files.

Template files to commit and share:

- `.env.example`
- `config/photo_sources.example.yaml`

## 3. Environment variables

`.env.example` is grouped by optional feature. Leave values blank for integrations you are not using.

| Variable | Required for | Secret? | Notes |
| --- | --- | --- | --- |
| `POST_RELAY_META_APP_ID` | Meta login/validation/publishing | No | Meta app client ID. |
| `POST_RELAY_META_APP_SECRET` | token extension/OAuth | Yes | Keep private. |
| `POST_RELAY_USER_ACCESS_TOKEN` | Meta validation/publishing/insights | Yes | User token for your Facebook user and Page access. |
| `POST_RELAY_FACEBOOK_PAGE_ID` | Meta validation/publishing | No | Your linked Facebook Page ID, not Andrew's. |
| `POST_RELAY_INSTAGRAM_ACCOUNT_ID` | Meta validation/publishing/analytics | No | Your professional IG account ID, not Andrew's. |
| `POST_RELAY_META_GRAPH_BASE_URL` | Meta integration | No | Defaults to `https://graph.facebook.com`. |
| `POST_RELAY_META_GRAPH_VERSION` | Meta integration | No | Defaults to the version in `.env.example`. |
| `POST_RELAY_TEST_IMAGE_URL` | optional publish validation | No | Must be a public HTTPS image URL. |
| `POST_RELAY_TEST_CAPTION` | optional publish validation | No | Smoke-test caption only. |
| `POST_RELAY_DISCORD_BOT_TOKEN` | live Discord DM sends | Yes | Optional. |
| `POST_RELAY_DISCORD_TARGET_USER_ID` | live Discord DM sends | No | Optional target Discord user ID. |
| `POST_RELAY_R2_ACCOUNT_ID` | R2 staging upload | No | Cloudflare account ID. |
| `POST_RELAY_R2_ACCESS_KEY_ID` | R2 staging upload | Yes | S3-compatible R2 access key ID. |
| `POST_RELAY_R2_SECRET_ACCESS_KEY` | R2 staging upload | Yes | S3-compatible R2 secret access key. |

## 4. Optional Meta/Instagram setup

Use this only after the local workflow is useful.

Requirements:

- Instagram professional Creator or Business account.
- Facebook Page linked to that Instagram account.
- Facebook user with access to the Page.
- Meta app credentials or beta tester access to a shared Post Relay app.
- Official Meta/Facebook Graph route. Do not use browser automation or unofficial posting methods.

For trusted beta users, use the OAuth helper instead of copying tokens from Graph API Explorer. The first command prints a Meta login URL without network calls; after the browser redirects to the configured callback URL, copy the `code` query parameter into the execute command:

```bash
.venv/bin/post-relay meta oauth-login --env-file .env
.venv/bin/post-relay meta oauth-login --env-file .env --execute --code OAUTH_CODE_FROM_REDIRECT
.venv/bin/post-relay meta oauth-login --env-file .env --execute --code OAUTH_CODE_FROM_REDIRECT --update-env --page-id YOUR_FACEBOOK_PAGE_ID --instagram-account-id YOUR_INSTAGRAM_ACCOUNT_ID
```

For the manual Graph API Explorer path, first populate your private user token in `.env`:

```bash
POST_RELAY_META_APP_ID=YOUR_META_APP_ID
POST_RELAY_META_APP_SECRET=YOUR_META_APP_SECRET
POST_RELAY_USER_ACCESS_TOKEN=YOUR_PRIVATE_USER_ACCESS_TOKEN
POST_RELAY_META_GRAPH_BASE_URL=https://graph.facebook.com
POST_RELAY_META_GRAPH_VERSION=v19.0
```

Then discover visible Pages and linked Instagram professional accounts. Dry-run prints the planned read-only requests without network calls:

```bash
.venv/bin/post-relay meta discover-accounts --env-file .env --dry-run
.venv/bin/post-relay meta discover-accounts --env-file .env --execute
```

After choosing the Page/IG pair from the output, update only the non-secret account ID fields in `.env`:

```bash
.venv/bin/post-relay meta discover-accounts --env-file .env --execute --update-env --page-id YOUR_FACEBOOK_PAGE_ID --instagram-account-id YOUR_INSTAGRAM_ACCOUNT_ID
```

Validate read-only first:

```bash
.venv/bin/post-relay meta validate-readonly --env-file .env --dry-run
```

If you have a fresh short-lived token and want to extend it, dry-run first:

```bash
.venv/bin/post-relay meta token-extend --env-file .env
```

Execute only when you intend to update your private `.env`:

```bash
.venv/bin/post-relay meta token-extend --env-file .env --execute --update-env
```

Live publish commands remain explicitly gated by approvals, schedule checks, public HTTPS media URLs, and `--execute`.

## 5. Optional Cloudflare R2 staging

Meta publishing needs public HTTPS media URLs. R2 staging is one way to make selected publish assets available to Meta.

For the first friend/beta round, use a bring-your-own-bucket setup. Managed staging is designed for later, but the current implementation already supports self-managed R2 well enough for technical users. The complete setup guide is `docs/byo-r2-bucket-setup.md`.

For your own R2 bucket:

1. Create or choose a Cloudflare R2 bucket dedicated to temporary Post Relay staging.
2. Create S3-compatible R2 credentials. A generic Cloudflare API token is not enough.
3. In Cloudflare, the credential path is `Storage & databases` -> `R2 Object Storage` -> `Overview` -> right-side `Account Details` -> `{}` `Manage` -> `Account API Tokens` -> `Create Account API Token`.
4. Configure `r2_staging` in `config/photo_sources.yaml` with your bucket, S3 endpoint URL, public base URL, and Post Relay-only prefix.
5. Put secrets in `.env`:

```bash
POST_RELAY_R2_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
POST_RELAY_R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
POST_RELAY_R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
```

Always inspect the plan first:

```bash
.venv/bin/post-relay drafts r2-stage-plan --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

Execute only after confirming the planned object count and keys are expected:

```bash
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute
```

Cleanup deletes only recorded uploaded objects under the configured Post Relay prefix:

```bash
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute --reason "publish complete"
```

## 6. Optional Discord DM workflow

Discord is optional. The local `dm` commands can model the workflow without live sends.

Live private DM sends require:

```bash
POST_RELAY_DISCORD_BOT_TOKEN=YOUR_DISCORD_BOT_TOKEN
POST_RELAY_DISCORD_TARGET_USER_ID=YOUR_DISCORD_USER_ID
```

Use local/no-network planning before live Discord commands:

```bash
.venv/bin/post-relay dm intake --message "start a post about Kyoto night market" --discord-channel-id local-test --db data/post_relay.sqlite
.venv/bin/post-relay dm next-action --discord-channel-id local-test --db data/post_relay.sqlite
```

## 7. Publishing safety model

Post Relay is intentionally guarded:

- Source media is never deleted, moved, or modified.
- Review artifacts and publish exports are derived local files.
- Most external workflows have dry-run or planning defaults.
- Live Meta publishing requires official Graph API routes.
- Live publish execution requires explicit `--execute`.
- Content approval and final publish approval are separate gates.
- Material edits invalidate active approvals.
- Scheduled publish execution checks due time before creating Meta containers.
- Freeform location text is local/review-only; only an explicitly reviewed Meta Page `location_id` may be sent as a publish location tag.

## 8. Current onboarding modes

| Mode | Who it is for | Requires |
| --- | --- | --- |
| Local preview | Anyone trying the photo review workflow | Python, local processed photo folder |
| Connected Meta tester | Trusted beta users who want account validation/publish previews | Meta app tester access, linked FB Page + professional IG account |
| Self-managed R2 staging | Users comfortable with Cloudflare | R2 bucket, S3 credentials, public domain/base URL |
| Managed staging | Future beta path | Not implemented yet; planned to avoid sharing raw R2 credentials |

For the product roadmap that lowers setup burden over time, see `docs/plans/product-onboarding-roadmap.md`.
