# Bring your own Cloudflare R2 bucket

Post Relay can publish through official Meta/Instagram Graph routes only when Meta can fetch the selected media from public HTTPS URLs. For this first friend/beta round, the simplest staging path is for each user to bring their own Cloudflare R2 bucket.

Local preview does not need R2. Set this up only after you have a reviewed post and want to test staging/publish preflight.

## What you need

- A Cloudflare account.
- One R2 bucket dedicated to temporary Post Relay staging.
- S3-compatible R2 access credentials for that bucket/account.
- A public HTTPS URL base for objects in the bucket, either a custom domain or another Cloudflare-supported public R2 URL path.

Important: a generic Cloudflare API token is not enough for Post Relay uploads. Post Relay's R2 upload path uses S3-compatible credentials:

- Access Key ID
- Secret Access Key
- Account ID
- Bucket name
- S3 endpoint URL
- Public base URL

## 1. Create or choose an R2 bucket

In Cloudflare:

1. Open the Cloudflare dashboard.
2. Go to `Storage & databases`.
3. Open `R2 Object Storage`.
4. Create a new bucket or choose an existing bucket you control.
5. Prefer a bucket dedicated to Post Relay staging so cleanup is easy to reason about.

Use a safe bucket/prefix strategy:

- Bucket: any private name you control, for example `my-post-relay-staging`.
- Prefix: a Post Relay-only prefix, for example `post-relay/staging`.
- Do not point Post Relay at a bucket/prefix that contains unrelated production files.

## 2. Find the Account ID and create R2 credentials

The R2 credential UI is easy to miss. Use this Cloudflare path:

1. Go to `Storage & databases`.
2. Open `R2 Object Storage`.
3. Click `Overview`.
4. On the right-side panel, find `Account Details`.
5. Click the `{}` `Manage` button.
6. In the page that opens, find `Account API Tokens`.
7. Click `Create Account API Token`.
8. Create a token for R2 object storage access.
9. Copy the generated S3-compatible values immediately:
   - Access Key ID
   - Secret Access Key

Also copy the Cloudflare Account ID from the Account Details area. The endpoint URL uses it:

```text
https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
```

Keep the Secret Access Key private. Put it only in your local `.env` file.

## 3. Configure public HTTPS access

Meta cannot fetch local files or authenticated R2 objects. The staged media must be reachable over public HTTPS.

Recommended options:

1. Configure a custom domain for the R2 bucket, for example:

```text
https://media.yourdomain.com
```

2. Or use a Cloudflare-supported public R2 URL if enabled for your bucket/account.

Whichever you choose, `public_base_url` in `config/photo_sources.yaml` must match the public URL prefix where uploaded objects can be fetched without cookies or auth headers.

Before live publish, verify a staged object URL opens in a private/incognito browser window.

## 4. Configure Post Relay

Edit your private `config/photo_sources.yaml`:

```yaml
r2_staging:
  enabled: true
  bucket: YOUR_R2_BUCKET_NAME
  endpoint_url: https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com
  public_base_url: https://YOUR_PUBLIC_R2_DOMAIN
  prefix: post-relay/staging
  default_ttl_hours: 72
  cleanup_after_publish: true
  account_id_env: POST_RELAY_R2_ACCOUNT_ID
  access_key_id_env: POST_RELAY_R2_ACCESS_KEY_ID
  secret_access_key_env: POST_RELAY_R2_SECRET_ACCESS_KEY
```

Edit your private `.env`:

```bash
POST_RELAY_R2_ACCOUNT_ID=YOUR_CLOUDFLARE_ACCOUNT_ID
POST_RELAY_R2_ACCESS_KEY_ID=YOUR_R2_ACCESS_KEY_ID
POST_RELAY_R2_SECRET_ACCESS_KEY=YOUR_R2_SECRET_ACCESS_KEY
```

Do not commit either file.

## 5. Run local diagnostics

The setup doctor checks whether the expected local files and env values are present without printing secrets:

```bash
.venv/bin/post-relay doctor --config config/photo_sources.yaml --db data/post_relay.sqlite --env-file .env
```

When `r2_staging.enabled` is true, the doctor checks self-managed R2 readiness without contacting Cloudflare:

- bucket name is present
- S3 `endpoint_url` is present
- public `public_base_url` is present
- the configured R2 env var names have local values
- the public base URL has not accidentally been set to the same S3 API endpoint URL

If the doctor reports `FAIL R2 endpoint/public URL separated`, keep `endpoint_url` as the S3 API URL (`https://YOUR_ACCOUNT_ID.r2.cloudflarestorage.com`) and set `public_base_url` to the unauthenticated public object URL base, such as your R2 custom domain.

If `boto3` is missing, install the project dependencies from the repo root:

```bash
.venv/bin/pip install -e ".[dev]"
```

## 6. Plan before upload

Always inspect the plan first. This should include selected post media only, preferably publish exports if you rendered them.

```bash
.venv/bin/post-relay drafts r2-stage-plan --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

Before executing, check:

- the media count matches the selected post media
- object keys are under your configured Post Relay prefix
- no source folders, review contact sheets, thumbnails, or unselected images are included
- public URLs are under the expected public base URL

## 7. Upload only after reviewing the dry run

```bash
.venv/bin/post-relay drafts r2-stage-upload --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute
```

After upload, run final publish preview/preflight from staged R2 before any live Meta publish execute:

```bash
.venv/bin/post-relay meta final-publish-preview --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay meta publish-scheduled --post-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite
```

These commands are still no-network publish preflights unless you explicitly add the live publish `--execute` command later.

## 8. Cleanup staged objects

Cleanup is dry-run by default and targets only recorded uploaded objects under the configured Post Relay prefix:

```bash
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup --post-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute --reason "publish complete"
```

Cleanup never deletes local source photos.

## Troubleshooting

Credential looks like a Cloudflare API token, not an Access Key ID:

- Revisit `Storage & databases` -> `R2 Object Storage` -> `Overview` -> right-side `Account Details` -> `{}` `Manage` -> `Account API Tokens` -> `Create Account API Token`.
- You need the S3-compatible Access Key ID and Secret Access Key pair.

Upload succeeds but Meta/public browser cannot fetch the URL:

- Check `public_base_url`.
- Confirm the bucket object is publicly accessible at that URL.
- Test the final object URL in a private/incognito browser window.
- Do not use the S3 endpoint URL as the public base URL; `https://ACCOUNT_ID.r2.cloudflarestorage.com` is for S3 API uploads, not necessarily public object fetching.

Dry-run includes too many files:

- Stop before `--execute`.
- Confirm the post media selection with:

```bash
.venv/bin/post-relay drafts media-plan --post-id 1 --db data/post_relay.sqlite
```

- Render publish exports if needed and rerun the R2 dry run.

Secret accidentally committed:

- Rotate the R2 token in Cloudflare immediately.
- Remove the secret from git history before sharing the repo further.
