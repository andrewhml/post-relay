# Post Relay Agent Handoff

This file is the repo-level handoff for AI agents working on Post Relay.

## Read first

Before making changes, read these files in order:

1. `README.md` — current project status, validated Meta setup facts, local CLI commands.
2. `docs/plans/current-agent-roadmap.md` — current completed milestones, next milestones, and execution rules.
3. `implementation-plan.md` — high-level phase plan from MVP through publishing and optimization.
4. `technical-design.md` — product architecture, safety rules, and component responsibilities.
5. `requirements.md` and `setup-checklist.md` — original requirements and setup notes.

## Project goal

Post Relay is a local-first Instagram travel content workflow for Andrew's `andrewhml` Creator account. It should help turn a processed travel photo backlog into reviewed, scheduled, and eventually published Instagram posts.

## Current architecture direction

- Python package under `src/post_relay/`.
- SQLite database, default local path `data/post_relay.sqlite`.
- CLI entry point: `post-relay`.
- Tests under `tests/`, run with `.venv/bin/python -m pytest -q`.
- Processed Lightroom/year folders are the primary source for the MVP.
- Immich/NAS can be added later as secondary enrichment, not as the v1 source of truth.
- Candidate groups are currently built from indexed photo parent folders.
- Multi-photo folders recommend `carousel`; one-photo folders recommend `single_image`.
- Draft records can be created idempotently from candidate groups.
- Draft preview packages can be rendered locally before Discord delivery exists.
- Draft context questions can be generated/listed locally and included in draft previews.
- Draft content direction can be submitted for review, approved for queueing, and invalidated by material edits.
- Dry-run Discord preview payloads can be generated locally with ordered existing image paths and missing-file reporting.
- Local draft review artifacts can be rendered with `drafts artifacts render`; generated thumbnails/contact sheets are written under the configured artifact root without modifying source media.
- No-network R2 staging plans can be generated with `drafts r2-stage-plan`; plans use sanitized object keys/public URLs, preserve included draft media order, and report missing local files before upload exists.
- R2 staging upload/cleanup can be dry-run locally; `drafts r2-stage-upload --execute` uploads and records planned objects, while `drafts r2-cleanup --execute` deletes only recorded uploaded objects under the configured Post Relay prefix.
- Numbered draft media plans and edits can be applied locally with `drafts media-plan` and `drafts media-edit`; lead/cover, keep/remove, and post-type changes update candidate media ordering/roles/inclusion and invalidate active approvals.
- Queue-approved drafts can be scheduled locally and moved through final publish approval without live API calls.
- Guarded single-image/carousel publish validation can use either explicit public HTTPS `--image-url` values or recorded uploaded R2 staged media via `--from-staged-r2`, preserving dry-run defaults, double approval, and explicit `--execute` publish safeguards.
- Live Discord delivery should only be added after the local payload harness remains green; next Discord work should first support Andrew selecting X photos from Y suggestions, then guide post type, caption/content, hashtags, location handling, schedule, and approvals before the live carousel smoke test.

## Safety and product constraints

- Never commit secrets or access tokens.
- Never paste tokens into chat or logs.
- Publishing must use official Meta/Instagram routes only.
- Do not use browser automation, password scraping, or unofficial posting methods.
- Treat `graph.facebook.com` as the validated primary Graph route for this account unless a later milestone documents a better supported route.
- Enforce double approval before live publishing:
  1. draft approval
  2. publish approval
- Never implement autonomous live posting without explicit publish approval.
- If a draft changes materially after approval, invalidate prior approvals.

## Workflow rules for agents

- Use rollback-safe milestone branches and PRs.
- Start every milestone from synced `main`.
- Use branch names like `feat/draft-records-from-candidates`, `docs/agent-roadmap`, or `fix/...`.
- Keep one milestone per PR.
- Use TDD for code changes:
  1. write failing tests first
  2. run the focused test and confirm it fails for the expected reason
  3. implement the minimum code
  4. run focused tests
  5. run the full suite
- For integration-like features such as Discord messaging or image previews, add narrow check-in tests before building the full integration. Prefer local/dry-run payload tests from a fixture photo directory before live Discord delivery.
- For docs-only changes, still run the existing test suite before merging.
- Squash merge PRs to `main`, delete the feature branch, then sync local `main` before starting another milestone.

## Useful commands

```bash
.venv/bin/python -m pytest -q
.venv/bin/post-relay db init --db data/post_relay.sqlite
.venv/bin/post-relay index scan --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay library stats --db data/post_relay.sqlite
.venv/bin/post-relay meta validate-readonly --env-file .env --dry-run
.venv/bin/post-relay meta validate-image-publish --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay meta validate-carousel-publish --draft-id 1 --from-staged-r2 --config config/photo_sources.yaml --db data/post_relay.sqlite --dry-run
.venv/bin/post-relay candidates build --db data/post_relay.sqlite
.venv/bin/post-relay candidates list --db data/post_relay.sqlite
.venv/bin/post-relay drafts create --candidate-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts list --db data/post_relay.sqlite
.venv/bin/post-relay drafts preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts artifacts render --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-plan --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts media-edit --draft-id 1 --lead 3 --keep 1,3,5 --post-type carousel --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-plan --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-stage-upload --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute
.venv/bin/post-relay drafts r2-cleanup --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite
.venv/bin/post-relay drafts r2-cleanup --draft-id 1 --config config/photo_sources.yaml --db data/post_relay.sqlite --execute --reason "publish complete"
.venv/bin/post-relay drafts discord-preview --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts submit --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve --draft-id 1 --approved-by andrew --notes "Content direction approved" --db data/post_relay.sqlite
.venv/bin/post-relay drafts edit --draft-id 1 --caption "Draft caption" --db data/post_relay.sqlite
.venv/bin/post-relay drafts schedule --draft-id 1 --scheduled-for "2026-05-05T09:30:00-07:00" --db data/post_relay.sqlite
.venv/bin/post-relay drafts request-publish-approval --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts approve-publish --draft-id 1 --approved-by andrew --notes "Final approval" --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions generate --draft-id 1 --db data/post_relay.sqlite
.venv/bin/post-relay drafts questions list --draft-id 1 --db data/post_relay.sqlite
```

## Current next milestone

See `docs/plans/current-agent-roadmap.md`. The next planned code milestone is currently `feat/discord-selection-model`, the first step in `docs/plans/discord-photo-selection-before-carousel-smoke.md`. This must start the guided workflow that lets Andrew choose X photos from Y suggested draft photos, then align on post type/content/metadata/schedule before the guarded live carousel smoke test milestone.
