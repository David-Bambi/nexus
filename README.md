# Milestone

A single-user, GTD-inspired project manager served as a local web app. You
capture ideas without friction, refine them later, and plan work into
versions that each deliver one complete feature — never a half-shipped one.

## Status

Project skeleton only. `main.py` is a placeholder and no Flask app, models,
or services exist yet. The full technical specification —
[`documents/specs/milestone-app-v1.md`](documents/specs/milestone-app-v1.md) —
is the source of truth for scope, data model, service signatures, HTTP
routes, and the increment plan. Read it before implementing anything.

## Requirements

- Python >= 3.12
- [`uv`](https://docs.astral.sh/uv/) for dependency management

## Setup

```bash
uv sync              # install dependencies from pyproject.toml / uv.lock
uv run main.py       # run the current entry point
```

## Architecture

The core constraint is layering (ADR-001): all business logic lives in
`src/services/`, which never imports Flask or anything request/session
related. It exposes plain Python functions that take simple arguments and
return domain objects or raise domain exceptions. Flask routes in `src/web/`
are thin adapters — validate input, call a service, render a template. A
future CLI and agentic interface will call the exact same service
functions, so no business rule may ever live in a route. This is enforced
by `tests/test_architecture.py`.

Other key decisions, detailed in the spec:

- **Append-only event log** (ADR-002) — every domain mutation writes an
  immutable row to an `event` table, powering per-task history, per-version
  changelogs, and future agent traceability.
- **Flask + Jinja + HTMX** (ADR-003) — SQLAlchemy/Alembic on SQLite, no JS
  build step.
- **Local-only binding** (ADR-004) — the server binds to `127.0.0.1` with no
  authentication in v1; that never changes without authentication shipping
  alongside it.

The domain model is `Project → Version → Task`, one-to-many at each level.
A task's `project_id` and `version_id` nullability drives the GTD workflow:
unset `project_id` means a raw capture, unset `version_id` means it's not
yet planned. Task states (`inbox → refined → planned → doing ↔ waiting →
done`, plus `someday`) and their transition rules are enforced in the
services layer — see spec §4.3.

## Versioning

Strict SemVer. `0.x.0` increments are pre-1.0 and unstable; `1.0.0` is
reserved for the increment that delivers the full v1 scope (spec §2). See
spec §12 for the increment table — each row is independently usable, not a
partial slice.
