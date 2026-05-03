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
- For docs-only changes, still run the existing test suite before merging.
- Squash merge PRs to `main`, delete the feature branch, then sync local `main` before starting another milestone.

## Useful commands

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
```

## Current next milestone

See `docs/plans/current-agent-roadmap.md`. The next planned code milestone is currently `feat/context-placeholders-and-questions` unless that roadmap has been updated.
