# Managed R2 Staging Design

**Status:** Design milestone for friend/beta onboarding. No implementation or live upload behavior is introduced by this document.

**Goal:** Let trusted Post Relay users publish through official Meta Graph routes without each user configuring raw Cloudflare R2 credentials, while keeping source media local, publish uploads explicit, staged objects disposable, and public URLs bounded by prefix/TTL/quota controls.

## Non-goals

- Do not replace local-first review, approval, scheduling, or publish validation.
- Do not store or proxy raw source libraries.
- Do not make R2/Meta/Discord mandatory for local preview value.
- Do not expose shared R2 account credentials to users or local `.env` files.
- Do not upload review artifacts, thumbnails, contact sheets, or unselected media by default.
- Do not publish to Instagram. Publishing remains a separate guarded Meta command with content approval plus final publish approval.

## Current self-managed baseline

Post Relay already supports self-managed staging:

- Users configure R2 bucket/domain/prefix in `config/photo_sources.yaml`.
- Users store S3-compatible `POST_RELAY_R2_ACCESS_KEY_ID` and `POST_RELAY_R2_SECRET_ACCESS_KEY` in private `.env`.
- `drafts r2-stage-plan` and `drafts r2-stage-upload` default to dry-run.
- `drafts r2-stage-upload --execute` uploads selected post media and records staged object metadata locally.
- `drafts r2-cleanup --execute` deletes only recorded uploaded objects under the configured Post Relay prefix.
- Meta publish validation can use `--from-staged-r2` to resolve public HTTPS URLs.

Managed staging should preserve these semantics while moving raw credentials out of the user's machine.

## Proposed architecture

Use a small managed staging service in front of a shared Cloudflare R2 bucket.

```text
Post Relay CLI
  -> Managed staging service
      -> Cloudflare R2 bucket under a Post Relay-owned prefix
  -> public HTTPS object URLs
  -> existing Meta publish validation/publish commands
```

The local CLI remains the source of truth for:

- selected media order
- selected publish exports versus original source files
- post type
- approvals
- schedule
- staged object records
- cleanup requests

The service owns:

- user identity checks
- upload authorization
- object key generation
- per-user/per-post quotas
- R2 credentials
- optional server-side cleanup sweeps
- audit metadata needed to delete staged objects safely

## User identity and authorization

For the MVP, avoid a broad public SaaS surface. Use trusted-user access only.

Recommended MVP identity options, in priority order:

1. **Static invite token per trusted user**
   - Stored locally as `POST_RELAY_MANAGED_STAGING_TOKEN`.
   - Server maps token to an opaque `user_id` and status.
   - Simple to operate for friends/beta users.

2. **OAuth-backed session later**
   - User signs into a Post Relay-managed identity provider.
   - CLI stores a refreshable staging token.
   - Better for broader distribution, not required for MVP.

The service must not treat Meta user tokens as staging authentication. Meta OAuth is for Meta API access; staging auth is a separate Post Relay concern.

## Upload authorization model

Use server-minted presigned upload URLs for the MVP.

Flow:

1. CLI builds the local staging plan from the selected post media, preferring publish exports when present.
2. CLI sends a planning request to the managed staging service containing only metadata required for authorization:
   - local post id
   - post media count
   - sanitized media basenames or extensions
   - byte sizes
   - MIME types
   - optional checksums
   - requested publish time or TTL class
3. Service validates user quota and returns one presigned PUT URL per approved media item plus final public URLs.
4. CLI uploads each selected file directly to R2 through the presigned URL.
5. CLI records staged object metadata locally only after upload success.
6. CLI can later call cleanup with object ids/keys that the service verifies against the authenticated user.

Why presigned URLs:

- raw R2 credentials never leave the service
- large media does not proxy through the service process
- object keys stay server-generated and sanitized
- per-object expiry and quotas are easy to enforce

Do not start with browser automation, shared credentials, or user-provided buckets for the managed path.

## Object key format

Managed keys should be opaque enough not to leak user names, source folders, travel locations, or filenames.

Recommended key shape:

```text
managed/v1/users/{user_id_hash}/posts/{post_uuid}/{media_index}-{random_token}.{ext}
```

Rules:

- `user_id_hash`: stable opaque hash or service-side id, not email/Discord/Instagram username.
- `post_uuid`: generated locally or by the service; should not be a sequential local DB id alone.
- `media_index`: 1-based order for auditability, not a filename.
- `random_token`: at least 128 bits of randomness or equivalent unguessable token.
- `ext`: derived from validated MIME type; do not trust raw local basename.
- Never include source folder names, original filenames, captions, locations, or account handles in keys.

## Public URL generation

Meta requires public HTTPS media URLs for publish containers.

Managed staging should return public URLs in the planning response only for objects the user is authorized to upload. The URL host should be a managed public domain such as:

```text
https://media.postrelay.example/managed/v1/users/.../posts/.../1-random.jpg
```

Constraints:

- URLs must be HTTPS.
- URLs must not require cookies or authorization headers because Meta must fetch them.
- URLs should remain valid through the scheduled publish window plus a cleanup buffer.
- URLs should not reveal private user identity or local filesystem details.
- If Cloudflare signed URLs are used later, confirm Meta can fetch them reliably before enabling; default MVP can rely on unguessable object keys plus TTL cleanup.

## TTL and cleanup policy

Staged media is disposable. Local source media remains canonical.

Recommended TTL classes:

- Immediate publish: 48 hours from upload.
- Scheduled publish: scheduled time plus 48 hours, capped by a maximum staging horizon.
- Maximum staging horizon for MVP: 14 days unless explicitly extended.

Cleanup controls:

- CLI cleanup command remains explicit and dry-run-first.
- Service accepts cleanup requests only for objects owned by the authenticated user.
- Service runs a periodic server-side sweeper for expired objects.
- Delete-after-publish remains best-effort and should not mutate local source files.
- Cleanup failures should surface as warnings and retryable records, not block local post history.

## Quotas and limits

Initial conservative defaults:

- Max media files per post: 10 for carousel parity.
- Max file size: align with current Meta image/video constraints before video support; start with images only unless a video milestone validates larger media.
- Max staged bytes per user: configurable, e.g. 2 GB for trusted beta users.
- Max active posts per user: configurable, e.g. 20 staged posts.
- Max retention: 14 days by default.
- Accepted MIME types: start with JPEG/PNG only; add video after Reel/video validation.

The CLI should display quota failures before upload when the service returns them.

## Local configuration shape

Add a new managed staging section separate from self-managed R2 config. Example future `config/photo_sources.yaml` shape:

```yaml
managed_staging:
  enabled: true
  endpoint: https://staging.postrelay.example
  public_base_url: https://media.postrelay.example
  default_ttl_hours: 48
```

Private `.env` value:

```bash
POST_RELAY_MANAGED_STAGING_TOKEN=YOUR_PRIVATE_INVITE_TOKEN
```

Do not reuse `POST_RELAY_R2_ACCESS_KEY_ID` or `POST_RELAY_R2_SECRET_ACCESS_KEY` for managed staging.

## Local database records

Reuse or extend the existing staged media record pattern, but distinguish providers.

Minimum fields for future implementation:

- post id
- candidate media id / local media id
- media order
- local source path or publish export path used at upload time
- provider: `self_managed_r2` or `managed_r2`
- service upload id or object id
- object key
- public URL
- MIME type
- byte size
- checksum if available
- status: planned, uploaded, failed, cleanup_requested, deleted, expired
- expires_at
- uploaded_at
- deleted_at
- sanitized error text

Staged records must not contain access tokens, presigned upload query strings, app secrets, or raw R2 credentials.

## CLI milestone shape for implementation

A future `feat/managed-r2-staging-mvp` should add managed equivalents without changing self-managed behavior:

- `drafts managed-stage-plan --post-id ...`
- `drafts managed-stage-upload --post-id ...`
- `drafts managed-stage-upload --post-id ... --execute`
- `drafts managed-stage-cleanup --post-id ...`
- `drafts managed-stage-cleanup --post-id ... --execute --reason ...`

Alternative: add `--managed` to existing R2 commands only if the output makes the provider unmistakable. Separate commands are safer for beta onboarding because they avoid confusing raw R2 credential requirements with managed staging tokens.

Dry-run output should show:

- selected media count and order
- whether publish exports are preferred and found
- total planned bytes
- endpoint and public base URL
- TTL/expiry plan
- quota status if service planning is executed
- exact provider: managed R2
- explicit statement that no Meta publish endpoints were called

## Failure modes and rollback

Common failures:

- Missing/invalid staging token.
- Service unavailable.
- Quota exceeded.
- Unsupported MIME type or file too large.
- Presigned upload expired.
- Partial upload success.
- Public URL not fetchable by Meta.
- Cleanup failed or object already deleted.

Rollback rules:

- Failed planning must not mutate post approvals, schedules, publish attempts, or source files.
- Failed upload should persist retryable per-object state only after explicit execute mode starts.
- Partial upload should allow cleanup of uploaded subset and retry of missing subset.
- Publish validation must require complete selected staged media before `--from-staged-r2` or future `--from-managed-staging` can proceed.
- Material post edits after staging should invalidate approvals as they do today; implementation should either restage or mark old staged records superseded.

## Privacy copy for beta users

Suggested user-facing copy:

> Managed staging uploads only the media files you selected for a reviewed post so Instagram can fetch them through official Meta publishing APIs. Your original photo library stays on your computer. Post Relay does not upload unselected folders, contact sheets, thumbnails, captions as files, or Lightroom/source metadata by default. Staged media is stored under randomized private-to-your-account object keys and is automatically cleaned up after the publish window.

Also disclose:

- public URLs are temporarily accessible to anyone who has the unguessable link
- staged copies are separate from local originals
- cleanup is best-effort and retried
- users can use self-managed R2 instead if they prefer owning bucket credentials

## Security checklist

- Raw R2 credentials exist only in service secrets.
- Invite/staging tokens are redacted in CLI output and errors.
- Object keys are generated by service code, not from local filenames.
- Presigned upload URLs are never persisted in SQLite.
- Public URLs use unguessable keys and bounded TTL cleanup.
- Cleanup validates authenticated ownership before deletion.
- Service logs redact tokens, presigned URL signatures, and local source paths.
- Local docs/templates do not include Andrew-specific bucket names, domains, IDs, or tokens.

## Testing checklist for future MVP

Local/domain tests:

- Managed plan includes selected media only, in order.
- Publish exports are preferred when present.
- Review artifacts/thumbnails/contact sheets are excluded.
- Object keys are sanitized and randomized.
- Quota errors are rendered without mutation.
- Dry-run makes no network calls and no DB writes beyond optional planned audit if intentionally designed.
- Execute uploads create records only for successful/attempted selected media.
- Cleanup only targets recorded managed objects owned by the user.
- Staged URL resolution refuses incomplete selected media.
- Secrets and presigned signatures are redacted from output and DB records.

Integration tests should use a fake staging service transport before any live Cloudflare/R2 test.

## Open decisions before implementation

- Whether the MVP service should be a Cloudflare Worker, small FastAPI service, or another deployment target.
- Exact invite-token issuance and revocation process.
- Whether planning should contact the service in dry-run mode for quota checks or remain fully local unless `--execute` is passed.
- Whether public URLs use plain unguessable R2 public access or signed URLs verified to work with Meta fetchers.
- Initial user quota values and maximum scheduling horizon.
- Whether to create separate CLI commands or a provider switch on existing staging commands.

## Recommended next milestone

For the first friend/beta round, do not implement managed staging yet. The BYO R2 setup docs and self-managed R2 doctor now cover the technical-user path. As of the post-PR #84 roadmap pause, leave `feat/managed-r2-staging-mvp` on hold unless Andrew explicitly reactivates this direction; near-term engineering should focus instead on smarter agent behavior and recommendation-engine foundations.
