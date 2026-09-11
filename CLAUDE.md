# CLAUDE.md

The file provides guidance to Claude code (claude.ai/code) when working in this repository.

Always respond write code or documents in english.

Keep your replies extremely concise and focus on conveying the key information. No unnecessary fluff, no long code snippets. 

All the artifacts generate by claude goes into @artifacts.

The source of truth is written in the documentation @docs. For each task keep the documentations in @docs updated.

## Nexus

The project nexus is a local webhost application to manage project.

## Project state

This repository currently contains only a project skeleton (`main.py` is a
placeholder) and a full technical specification for the application to be
built, "Milestone" — a single-user, GTD-inspired project manager served as a
local web app.

## Commands

The project uses `uv` for dependency management (Python >= 3.12).

```bash
uv sync              # install dependencies from pyproject.toml / uv.lock
uv run main.py       # run the current entry point
```

No test runner, linter, or Flask app factory exists yet — they will be
introduced as implementation proceeds per the spec's increment plan (see
`documents/specs/milestone-app-v1.md` §9 for the target tree and §10 for the
testing strategy).

## Architecture (target, per the spec)

**Layering is the core constraint (ADR-001).** All business logic lives in
`src/services/`, which must never import Flask or anything request/session
related — it exposes plain Python functions taking simple arguments and
returning domain objects or raising domain exceptions. Flask routes in
`src/web/` are thin adapters: validate input, call a service, render a
template. This is enforced by `tests/test_architecture.py`, which fails the
build if `services/` imports Flask. The reason this matters: a future CLI
and agentic interface will call the exact same service functions, so no
business rule may ever live in a route.

**Stack (ADR-003):** Flask + Jinja + HTMX for the web layer, SQLAlchemy +
Alembic for persistence, SQLite as the engine. No JS build step, no npm —
HTMX is served locally.

**Event log (ADR-002):** every domain mutation writes an immutable row to
an append-only `event` table (never updated or deleted). This is what
powers per-task history, per-version changelogs, and — later — traceability
of agent actions. The `actor` field is `"web"` in v1.

**Network binding (ADR-004):** the server binds to `127.0.0.1` only, with
no authentication in v1. Never change this without also adding auth — the
two ship together, never separately.

**Domain model:** `Project → Version → Task`, one-to-many at each level.
Nullability on `Task.project_id` / `Task.version_id` is the mechanism
behind the GTD workflow, not an edge case to special-case away:
- `project_id IS NULL` → raw capture, not yet attached to a project
- `version_id IS NULL` → not yet planned (needs refining)
- both set → planned into a milestone

Task states (`inbox → refined → planned → doing ↔ waiting → done`, plus
`someday`) and their transition rules are defined in the spec §4.3 and must
be enforced in the services layer, not just at the database level (e.g.
`waiting` requires a non-empty `blocked_reason`; only `planned`+ states may
have a null `version_id`; completing a version is refused unless every task
is `done`).

**Versioning of the app itself** follows strict SemVer: `0.x.0` increments
are pre-1.0 and considered unstable; `1.0.0` is reserved for the increment
that delivers the full v1 scope from spec §2. See spec §12 for the full
increment table — each row is meant to be independently usable, not a
partial slice.
