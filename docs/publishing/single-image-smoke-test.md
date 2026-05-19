# Controlled single-image publish smoke test

This runbook is for the first live Post Relay publish through the official Meta Graph route.

## Safety invariants

- Use only the official `graph.facebook.com` route.
- Do not paste tokens or app secrets into chat, commits, logs, or screenshots.
- Do not run the live command unless Andrew explicitly authorizes it in the active session.
- The post must already be `ready_to_publish`, which means it passed both content approval and publish approval.
- Start with `--dry-run`; only run `--execute` after the dry-run output is reviewed.

## Required local setup

A private `.env` file or shell environment must provide:

```bash
POST_RELAY_USER_ACCESS_TOKEN=<private token>
POST_RELAY_INSTAGRAM_ACCOUNT_ID=17841400498120050
POST_RELAY_META_GRAPH_BASE_URL=https://graph.facebook.com
POST_RELAY_META_GRAPH_VERSION=v19.0
POST_RELAY_TEST_IMAGE_URL=<public HTTPS image URL for the exact safe test image>
```

The test image URL must be publicly reachable by Meta. Local filesystem paths are not accepted by the Graph media container endpoint.

`POST_RELAY_TEST_CAPTION`, if present in `.env`, is only a local smoke-test helper value. The live publish command publishes the caption stored on the draft record, not the caption from `.env`.

## Required draft state

The draft must satisfy all of these:

- `post_type = single_image`
- exactly one selected candidate image
- non-empty caption
- active draft approval exists
- active publish approval exists
- `status = ready_to_publish`

Useful local flow for preparing a draft:

```bash
.venv/bin/post-relay drafts create --candidate-id <single-image-candidate-id> --db data/post_relay.sqlite
.venv/bin/post-relay drafts edit --post-id <post-id> --caption "Post Relay validation test" --db data/post_relay.sqlite
.venv/bin/post-relay drafts submit --post-id <post-id> --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --post-id <post-id> --approved-by andrew --notes "Content direction approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts schedule --post-id <post-id> --scheduled-for "2026-05-05T09:30:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve-publish --post-id <post-id> --approved-by andrew --notes "Final smoke-test approval" --db data/post_relay.sqlite
```

## Preflight check

Run the readiness helper. It prints only yes/no configuration status and draft ids; it does not print secret values.

```bash
.venv/bin/python scripts/check_publish_smoke_readiness.py
```

Expected before live execution:

```text
.env exists: yes
POST_RELAY_USER_ACCESS_TOKEN configured: yes
POST_RELAY_INSTAGRAM_ACCOUNT_ID configured: yes
POST_RELAY_TEST_IMAGE_URL configured: yes
database exists: yes
ready single-image drafts with caption: 1
ready draft ids: <draft-id>
```

## Dry run

```bash
.venv/bin/post-relay meta validate-image-publish \
  --post-id <post-id> \
  --image-url "$POST_RELAY_TEST_IMAGE_URL" \
  --db data/post_relay.sqlite \
  --dry-run
```

Review that:

- output starts with `Single-image publish validation`
- status is `planned`
- the image URL is sanitized if it contains secret-like query params
- output says `No Meta publishing endpoints were called.`

## Live execution

Only after Andrew explicitly authorizes the live smoke test:

```bash
.venv/bin/post-relay meta validate-image-publish \
  --post-id <post-id> \
  --image-url "$POST_RELAY_TEST_IMAGE_URL" \
  --db data/post_relay.sqlite \
  --env-file .env \
  --execute
```

Expected success indicators:

- `Status: published`
- `Container ID: <meta container id>`
- `Container status: FINISHED`
- `Published media ID: <meta media id>`
- draft status moves to `posted`

## Verification after execution

```bash
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/python -m pytest -q
```

Record the observed Meta behavior, sanitized ids/statuses, and any account/app limitation in `docs/plans/current-agent-roadmap.md`.

## Current local smoke result

Checked on 2026-05-03 with Andrew-provided private `.env`, the public GitHub raw smoke-test image URL, and a local ready single-image draft.

```text
.env exists: yes
POST_RELAY_USER_ACCESS_TOKEN configured: yes
POST_RELAY_INSTAGRAM_ACCOUNT_ID configured: yes
POST_RELAY_TEST_IMAGE_URL configured: yes
database exists: yes
draft count: 1
ready single-image drafts with caption: 1
ready draft ids: 1
```

Observed live execution:

```text
Status: published
Container ID: 18585234496016605
Container status: FINISHED
Published media ID: 18085108061165756
```

Implementation notes discovered during the smoke test:
- The linked Instagram account read endpoint did not accept `account_type`; read-only validation now requests `id,username,media_count` and renders account type as `<unknown>`.
- Meta media container creation and media publish endpoints require POST. Using GET did not create a container and returned no media container id.
- The caption configured in `.env` was not picked up by the actual live post. This is expected for the longer-term workflow because publish execution uses the approved draft caption stored in SQLite; `.env` should not be treated as the source of truth for post content.
