# Content Pipeline with R2 Staging Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Use one rollback-safe branch and PR per milestone.

**Goal:** Build a safe content pipeline that indexes local and NAS photo folders, produces review assets, stages publish-ready media to Cloudflare R2, and cleans only staged cloud copies after successful publishing.

**Architecture:** Local and NAS folders remain the durable source of truth and are never deleted or modified by cleanup commands. Post Relay stores indexed source paths in SQLite, creates local review artifacts such as thumbnails/contact sheets, optionally stages review/publish artifacts to an R2 bucket, and passes short-lived or explicitly generated HTTPS object URLs to Meta Graph publish commands. R2 is a temporary staging and review-delivery layer, not canonical storage.

**Tech Stack:** Python 3.9+, SQLite, Typer, Pydantic, PyYAML, Pillow, pytest, Cloudflare R2 S3-compatible API, boto3 or botocore-compatible S3 client, official Meta Graph publishing route.

---

## Product decisions

1. Local and NAS folders are authoritative. Post Relay must never delete, move, or mutate original media files.
2. The initial MVP indexes processed local/NAS folders; Immich remains future enrichment only.
3. R2 stores disposable staging objects:
   - publish candidates copied from local/NAS when a draft reaches publish validation
   - optional thumbnails/contact sheets for Discord review if direct Discord attachments are unreliable
4. R2 cleanup is allowed only for objects created by Post Relay under its configured prefix.
5. R2 cleanup is allowed after publish success, explicit draft cancellation, or explicit operator cleanup command.
6. R2 object keys must avoid leaking local absolute paths. Use stable draft/source ids and sanitized filenames.
7. R2 URLs must be persisted as sanitized URLs in audit records. Access keys, secrets, signed query credentials, and local private paths must not appear in logs, commits, Discord text, or PR bodies.
8. Meta publishing still requires double approval and explicit execution. R2 staging does not weaken publish guards.

## Proposed pipeline

```text
Local processed folders + NAS processed folders
    -> index scan
    -> candidate groups
    -> drafts
    -> local thumbnails/contact sheets
    -> Discord dry-run/review payload
    -> draft approval
    -> schedule + publish approval
    -> R2 publish staging
    -> Meta Graph publish using HTTPS R2 object URLs
    -> publish audit
    -> R2 cleanup for staged objects only
```

## Suggested config shape

Extend the private config pattern with separate source, artifact, and staging sections:

```yaml
photo_sources:
  - name: local-processed-2024
    root: /Users/andrewlee/Pictures/Processed/2024
    source_type: processed_folder
    enabled: true
    reliability_score: 1.0

  - name: nas-processed-2023
    root: /Volumes/Photos/Processed/2023
    source_type: processed_folder
    enabled: true
    reliability_score: 1.0

review_artifacts:
  root: data/review_artifacts
  thumbnail_max_px: 1600
  contact_sheet_columns: 3
  mode: local
  # Later: mode can become local, r2, or both.

r2_staging:
  enabled: false
  bucket: post-relay-staging
  account_id_env: POST_RELAY_R2_ACCOUNT_ID
  access_key_id_env: POST_RELAY_R2_ACCESS_KEY_ID
  secret_access_key_env: POST_RELAY_R2_SECRET_ACCESS_KEY
  public_base_url_env: POST_RELAY_R2_PUBLIC_BASE_URL
  prefix: post-relay/staging
  default_ttl_hours: 72
  cleanup_after_publish: true
```

Private `.env` values should include only secrets and deployment-specific endpoints:

```bash
POST_RELAY_R2_ACCOUNT_ID=<cloudflare-account-id>
POST_RELAY_R2_ACCESS_KEY_ID=<r2-access-key-id>
POST_RELAY_R2_SECRET_ACCESS_KEY=<r2-secret-access-key>
POST_RELAY_R2_PUBLIC_BASE_URL=https://<public-hostname-or-r2-dev-domain>
```

## Milestone 1: `feat/content-pipeline-config`

**Goal:** Teach Post Relay how to model local/NAS sources, review artifact settings, and disabled-by-default R2 staging config without making network calls.

**Acceptance criteria:**
- `config/photo_sources.example.yaml` documents local and NAS processed-folder entries.
- Config loader validates `review_artifacts` and `r2_staging` sections.
- R2 config defaults to disabled and never requires secrets unless a staging command needs them.
- Tests cover local/NAS paths, R2 defaults, environment variable names, and no-secret config rendering.
- Full suite passes.

**Implementation steps:**
1. Write failing config loader tests in `tests/test_config_loader.py` or a new `tests/test_pipeline_config.py`.
2. Run the focused test and confirm it fails because `review_artifacts` / `r2_staging` are not modeled.
3. Extend `src/post_relay/config.py` with `ReviewArtifactsConfig` and `R2StagingConfig` Pydantic models.
4. Update `config/photo_sources.example.yaml` with local/NAS/R2 examples using placeholders only.
5. Run focused tests, then `.venv/bin/python -m pytest -q`.
6. Update README and roadmap with the new config shape.

## Milestone 2: `feat/review-artifact-generation` (completed in PR #22)

**Goal:** Generate local thumbnails and contact sheets for draft review without mutating original media.

**Acceptance criteria:**
- A CLI command can render review artifacts for a draft, e.g. `drafts artifacts render --draft-id N --db ... --config ...`.
- Generated files live under configured `review_artifacts.root`.
- Thumbnails preserve ordering from the draft candidate items.
- Contact sheets include draft id, source title, and ordered media positions where feasible.
- Original local/NAS image files are opened read-only and never modified.
- Rendering rejects artifact roots that overlap configured source roots, so misconfiguration cannot create generated files inside a source media tree.
- Implemented files: `src/post_relay/review_artifacts.py`, `drafts artifacts render`, `tests/test_review_artifacts.py`, and a CLI artifact-render test.
- Tests use fixture images and assert output file existence, dimensions, and ordering.

**Implementation steps:**
1. Write RED tests with fixture images under `tests/fixtures/`.
2. Implement `src/post_relay/review_artifacts.py` using Pillow.
3. Add repository/artifact record storage only if needed for stable reuse; otherwise deterministic paths are enough for MVP.
4. Add CLI command and dry-run text output.
5. Update Discord preview payload to include local artifact paths as review attachments once generated.
6. Verify focused artifact tests and full suite.

## Milestone 3: `feat/r2-staging-dry-run`

**Goal:** Add a no-network R2 staging plan that shows exactly which files would be uploaded and what public keys/URLs would be used.

**Acceptance criteria:**
- CLI command plans staging for a draft without uploading by default.
- Planned object keys do not expose local absolute paths.
- Plan validates that source files exist locally or on mounted NAS.
- Plan validates one staged publish image per draft image.
- Plan output redacts any secret-like URL query parameters.
- Tests cover single-image, carousel ordering, missing source files, and sanitized output.

**Possible command:**

```bash
.venv/bin/post-relay staging r2-plan \
  --draft-id <draft-id> \
  --db data/post_relay.sqlite \
  --config config/photo_sources.yaml
```

## Milestone 4: `feat/r2-staging-upload-and-cleanup`

**Goal:** Upload selected draft media/artifacts to R2 and clean up only Post Relay-created staged objects.

**Acceptance criteria:**
- Upload requires an explicit `--execute` flag.
- Upload loads R2 credentials only from environment/private `.env`.
- Upload is injectable/testable with a fake S3 client; unit tests do not call Cloudflare.
- Staged object records are persisted with draft id, source file id/path reference, object key, sanitized public URL, purpose, status, and timestamps.
- Cleanup only deletes object keys recorded in the staging table and under the configured prefix.
- Cleanup has dry-run output by default and requires `--execute` for deletion.
- No local/NAS source files are ever deleted.

**Possible commands:**

```bash
.venv/bin/post-relay staging r2-upload --draft-id <draft-id> --db data/post_relay.sqlite --config config/photo_sources.yaml --env-file .env --execute
.venv/bin/post-relay staging r2-cleanup --draft-id <draft-id> --db data/post_relay.sqlite --config config/photo_sources.yaml --dry-run
.venv/bin/post-relay staging r2-cleanup --draft-id <draft-id> --db data/post_relay.sqlite --config config/photo_sources.yaml --env-file .env --execute
```

## Milestone 5: `feat/publish-from-staged-r2`

**Goal:** Let the existing Meta publish validation commands consume staged R2 URLs for single-image and carousel drafts.

**Acceptance criteria:**
- Existing `meta validate-image-publish` and `meta validate-carousel-publish` guards remain unchanged.
- A draft can resolve its staged publish URLs from persisted staging records.
- Dry-run publish output shows sanitized R2 URLs and still calls no Meta endpoints.
- Live publish uses only staged HTTPS URLs and the approved draft caption.
- After successful publish, optional cleanup can remove staged R2 objects, never local/NAS files.
- Tests cover publish URL resolution, cleanup-after-success flow, failed publish retaining staged objects for debugging, and carousel ordering.

## Milestone 6: `feat/discord-review-delivery`

**Goal:** Deliver review packages to Discord using local attachments first, with optional R2-hosted thumbnails/contact sheets if direct media delivery is unreliable.

**Acceptance criteria:**
- Live Discord delivery remains separate from dry-run preview.
- Dry-run payload harness stays green and remains the required preflight.
- Delivery mode is configurable: local attachments, R2 URLs, or both.
- No publish staging cleanup removes review artifacts still needed for active review.

## Data model additions to consider

### `review_artifacts`

- `id`
- `draft_id`
- `artifact_type` (`thumbnail`, `contact_sheet`)
- `local_path`
- `source_photo_id` nullable for contact sheets
- `width`
- `height`
- `created_at`

### `staged_objects`

- `id`
- `draft_id`
- `photo_id` nullable for contact sheets
- `purpose` (`publish_media`, `review_thumbnail`, `review_contact_sheet`)
- `local_source_path` or source photo id reference
- `object_key`
- `public_url_sanitized`
- `status` (`planned`, `uploaded`, `published`, `cleanup_planned`, `deleted`, `failed`)
- `created_at`
- `uploaded_at`
- `deleted_at`
- `last_error_sanitized`

## Safety test checklist

Every milestone touching staging or publishing must prove:

- Original source files still exist after staging and cleanup tests.
- Cleanup refuses keys outside the configured Post Relay prefix.
- Cleanup refuses objects not recorded in Post Relay's staging table.
- Secrets are loaded only from `.env`/environment and never from tracked YAML.
- CLI defaults are dry-run/no-network/no-delete.
- `--execute` is required for R2 upload/delete and Meta publish.
- Failed Meta publish leaves staged objects in place unless Andrew explicitly cleans them up.

## Open setup questions for Andrew

1. Final local processed-folder root path(s): `/Users/andrewlee/Pictures/2025 Photos/Processed` is configured as `local-processed-2025`; add other year folders as needed.
2. Final NAS mount path(s): `/Volumes/Media/photos/2024 Photos/Processed` is configured as `nas-processed-2024`; add other year folders as needed.
3. R2 bucket/public route: bucket `post-relay-publish`, S3 API endpoint `https://d79fef40225063d4b0e2d2cb33b346d0.r2.cloudflarestorage.com`, custom public domain `https://peddocks.net`.
4. Preferred R2 object TTL / cleanup window.
5. Whether review artifacts should be local-only first, R2-only, or both.
6. Whether contact sheets should include captions/metadata overlays or only image grids in the first version.
