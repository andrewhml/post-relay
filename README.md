# Post Relay

Local-first Instagram content workflow for Andrew's `andrewhml` creator account.

## Current status
Early local-first MVP scaffold with:
- SQLite schema for sources, photos, candidate groups, drafts, and approvals
- local photo source config loading
- folder-based media indexing
- library statistics CLI
- candidate group builder/list CLI
- draft create/list/preview CLI
- draft context question generate/list CLI
- draft approval/edit CLI with approval invalidation on material edits
- guarded draft workflow state model

## Proven setup facts
- Meta app: Post Relay
- App ID: `936195858780647`
- Facebook Page ID: `998312870038313`
- Instagram Account ID: `17841400498120050`
- Working auth/read route: `graph.facebook.com`
- `graph.instagram.com` returned `Invalid platform app` in current setup

## Immediate goals
1. Build local draft/queue data model
2. Build Discord review workflow
3. Validate publish container creation safely

## Agent handoff
Future agents should start with `AGENTS.md`, then `docs/plans/current-agent-roadmap.md`.

## Local CLI
Use the project virtualenv when running locally:

```bash
.venv/bin/python -m pytest -q
.venv/bin/post-relay db init --db data/post_relay.sqlite
.venv/bin/post-relay index scan --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay library stats --db data/post_relay.sqlite
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts submit --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --draft-id 1 --approved-by andrew --notes "Content direction approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts edit --draft-id 1 --caption "Draft caption" --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions generate --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions list --draft-id 1 --db data/post_relay.sqlite
```

Candidate groups currently use the indexed photo file's parent folder as the first reviewable travel set boundary. A folder with multiple photos is recommended as a carousel; a one-photo folder is recommended as a single image post. Draft records can be created from candidate groups and start in the `drafting` state with placeholder caption/location/hashtag fields. Draft preview packages print a stable local review format with ordered photo paths, unresolved context notes, persisted context questions, and allowed next actions before Discord delivery is added. Drafts can be submitted for review, approved for queueing, and edited locally; material edits after approval invalidate active approvals and move the draft back to `needs_edits`.

Discord/image-preview development should use check-in tests before live messaging: start with a local directory of fixture photos, verify the dry-run payload includes the expected image paths/order, then smoke-test Discord delivery only after the local payload behavior is stable.

## Local secrets
Use a private `.env` file based on `.env.example`.
Do not paste tokens or secrets into chat.
