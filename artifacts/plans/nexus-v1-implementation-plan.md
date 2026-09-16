# Nexus v1 — Implementation Plan & Todo List

## Context

`artifacts/specs/milestone-app-v1.md` is the full technical spec for Nexus
("Milestone"): a single-user, GTD-inspired project manager. The repo is
currently a bare skeleton — `src/main.py` is a `print("Hello from nexus!")`
stub, and `pyproject.toml` only declares `flask` and `htmx` as runtime deps.
No models, services, routes, tests, or migrations exist yet.

The spec already defines the right unit of work: six independently-usable
SemVer increments (§12), each with its own "definition of done." This plan
adopts that structure as the master todo list, and front-loads full
file-by-file detail only on **0.1.0** — the next and only increment
buildable against the current empty skeleton. Increments 0.2.0+ depend on
concrete decisions (exact service signatures, route wiring) that are
cleaner to re-plan once 0.1.0's actual code exists to build on, rather than
speculatively detailing them now against code that doesn't exist yet.

## Master todo list — increment roadmap (spec §12)

- [x] **0.1.0 — Foundation.** Flask factory, SQLAlchemy, Alembic, all 5
      models, base template, empty home page. *DoD: `flask run` starts, the
      database gets created, the page responds.* → fully detailed below.
- [x] **0.2.0 — Projects & versions.** `services/projects.py`,
      `services/versions.py`, CRUD, list/detail pages. *DoD: a project and
      its versions can be created and viewed from the browser.*
- [x] **0.3.0 — Tasks.** Full task state machine (§4.3) and transitions,
      global capture, version board, task detail (no history yet). *DoD:
      every transition in the state diagram is triggerable from the UI;
      every task has a detail page.*
- [x] **0.4.0 — Inbox, refine & search.** Dedicated inbox/refine views,
      context/project filters, global search, sequential processing. *DoD:
      a captured idea can reach a version without touching the DB by hand;
      a task is findable via search.*
- [ ] **0.5.0 — Dashboard, traceability & data.** Overview dashboard
      (in-progress versions, `doing`/`waiting` tasks, inbox/refine
      counters), event log wired to every mutation, per-task history, JSON
      export. *DoD: the dashboard reflects real system state; the app's own
      backlog can move into the app (§1 success criterion).*
- [ ] **1.0.0 — Operational hardening.** Service install (systemd/launchd/
      Windows task), backups, log rotation, autostart. *DoD: after a
      machine reboot, the app is available unattended — full v1 scope
      shipped.*

Each increment should get its own detailed plan (same process as below)
when it's actually picked up, since it will build on the real code from
prior increments, not just the spec.

## Detailed plan — Increment 0.1.0 (Foundation)

### Design decisions this plan makes

- **Absolute imports, explicit packages.** `src/`, `src/models/`,
  `src/services/`, `src/web/` get `__init__.py` files; import everywhere as
  `from src.models.project import Project`, etc. The project is a *virtual*
  uv project (no `[build-system]`), so this is the predictable way to make
  `src.*` resolve for Flask's CLI, Alembic, and pytest alike.
- **Template/static location.** `Flask(__name__)` in `src/app.py` defaults
  `root_path` to `src/`, so `create_app()` must explicitly pass
  `template_folder="web/templates"`, `static_folder="web/static"` to match
  the spec's tree (`src/web/templates`, `src/web/static`).
- **Run command:** `FLASK_APP=src.app:create_app uv run flask run` from the
  repo root — plain `flask run` auto-discovery won't find `src/app.py`.
- **Migrations run automatically at app startup** (`alembic.command.upgrade
  ... "head"` inside `create_app()`), per NFR §8 and so the DoD's "database
  gets created" is satisfied by one command (`flask run`), not a manual
  `alembic upgrade` step. Idempotent, so safe on every restart.
- **`services/` stays empty** (just `__init__.py`) in 0.1.0 — all business
  logic modules are explicitly deferred to 0.2.0+ per §12. `test_architecture.py`
  is still created now so the ADR-0001 guard exists from day one.
- **Only `base.html` + one trivial `/` route.** No dashboard/inbox/refine
  templates yet — those belong to later increments.
- **Config via env vars:** `NEXUS_DATABASE_URL` (default
  `sqlite:///<repo_root>/instance/nexus.db`), `NEXUS_SECRET_KEY`. The final
  `~/.milestone/data.db` path from §8 is a later NFR concern, not 0.1.0.
- **Note:** the `htmx>=0.0.0` package already in `pyproject.toml` is an
  unrelated placebo package (not the htmx.org library). Not touched in
  0.1.0 since no fragments exist yet — real HTMX integration will need the
  JS file vendored under `src/web/static/` in a later increment.

### Files, in dependency order

1. **Dependencies** — `uv add sqlalchemy alembic`, `uv add --dev pytest`
   (let `uv` pick current compatible versions, matching the existing
   `flask>=3.1.3` bare-lower-bound style). Add to `pyproject.toml`:
   ```toml
   [tool.pytest.ini_options]
   pythonpath = ["."]
   testpaths = ["tests"]
   ```
   Add `instance/` to `.gitignore`.

2. **Package markers** — `src/__init__.py`, `src/models/__init__.py`,
   `src/services/__init__.py` (docstring noting ADR-0001: never import
   flask here), `src/web/__init__.py`.

3. **`src/config.py`** — `Config` (env-driven `SECRET_KEY`,
   `DATABASE_URL`) and `TestConfig` (`sqlite:///:memory:`). Plain
   `os`/`pathlib`, no Flask import — reusable from Alembic's `env.py`.

4. **`src/db.py`** — `Base(DeclarativeBase)`, `get_engine(database_url)`,
   `get_session_factory(engine)` (scoped session). No Flask import.

5. **Models** (all attach to `src.db.Base`), in this order:
   - `src/models/project.py` — `Project`: `id`, `key` (unique), `name`,
     `description`, `status`, `created_at`; relationships to versions/tasks.
   - `src/models/tag.py` — `task_tag_table` (association table) + `Tag`:
     `id`, `name` (unique).
   - `src/models/version.py` — `Version`: `id`, `project_id` (FK, not
     null), `number`, `title`, `goal`, `definition_of_done`, `status`,
     `position`, `target_date`, `released_at`.
   - `src/models/task.py` — `Task`: `id`, `project_id` (FK, **nullable**),
     `version_id` (FK, **nullable**), `title`, `body`, `state`, `context`,
     `size`, `position`, `blocked_reason`, `created_at`, `updated_at`,
     `closed_at`; many-to-many `tags` via `task_tag_table`.
   - `src/models/event.py` — `Event`: `id`, `at`, `actor`, `entity_type`,
     `entity_id`, `action`, `payload` (JSON). No FKs (append-only, per
     ADR-0002).
   - `src/models/__init__.py` — import all five model classes so
     `Base.metadata` is fully populated from one import.

6. **Alembic wiring** — `uv run alembic init src/migrations`; edit
   `src/migrations/env.py` to add the repo root to `sys.path`, import
   `Config` and `src.models.Base`, set `target_metadata = Base.metadata`,
   and set the SQLAlchemy URL from `Config.DATABASE_URL` (single source of
   truth, not duplicated in `alembic.ini`). Generate + apply:
   ```bash
   uv run alembic revision --autogenerate -m "create initial schema"
   uv run alembic upgrade head
   ```

7. **App factory, route, template** — `src/web/templates/base.html`
   (minimal skeleton, empty `content` block); `src/web/routes_pages.py`
   (`Blueprint("pages", ...)`, `/` renders `base.html`, no model/service
   imports); `src/app.py` — `create_app()` builds the Flask app with the
   template/static paths above, ensures `instance/` exists, runs the
   Alembic upgrade, sets up the scoped-session teardown, registers the
   blueprint.

8. **Tests** — `tests/conftest.py` (`app`/`client` fixtures, in-memory
   DB via `Base.metadata.create_all`, not full Alembic replay);
   `tests/web/test_pages.py` (`GET /` → 200); `tests/test_architecture.py`
   (AST-walk `src/services/**/*.py`, fail if anything imports `flask` or
   `src.web` — the ADR-0001 guard, executable from day one even though
   `services/` is empty).

### End-to-end verification (= the 0.1.0 definition of done)

```bash
uv sync
rm -f instance/nexus.db
FLASK_APP=src.app:create_app uv run flask run --host 127.0.0.1 --port 8765 &
sleep 1
curl -i http://127.0.0.1:8765/                      # expect HTTP 200
uv run python -c "import sqlite3; con=sqlite3.connect('instance/nexus.db'); \
print(sorted(r[0] for r in con.execute(\"select name from sqlite_master where type='table'\")))"
# expect: ['alembic_version', 'event', 'project', 'tag', 'task', 'task_tag', 'version']
kill %1
uv run pytest -q                                    # architecture guard + smoke test green
```

### Critical files

- `src/db.py`, `src/config.py`
- `src/models/__init__.py` (+ the 5 model files)
- `src/migrations/env.py`
- `src/app.py`, `src/web/routes_pages.py`, `src/web/templates/base.html`
- `tests/test_architecture.py`, `tests/conftest.py`
- `pyproject.toml` (new deps + pytest config)

### After 0.1.0 lands

Per root `CLAUDE.md`, hand off to the `docs-manager` agent to update
`docs/architecture/overview.md` / ADRs if anything here diverges from what
they currently say, and to check off this increment before starting 0.2.0.

## Detailed plan — Increment 0.4.0 (Inbox, refine & search)

0.2.0 and 0.3.0 are done: projects/versions CRUD and the full task state
machine (`services/tasks.py`) both exist and are wired into
`routes_pages.py`. This increment adds the read side the spec calls
`services/views.py`, plus the three dedicated pages that turn raw
capture into planned work: the inbox (sequential triage), the refine
queue (bridge to planning), and search.

### Design decisions this plan makes

- **`services/views.py` gets only the three functions 0.4.0 needs** —
  `inbox(session)`, `to_refine(session, context=None, project_key=None)`,
  `search(session, term)`. The spec also lists `dashboard()` and
  `version_board()` in this module, but those belong to 0.5.0
  (dashboard/traceability) and are deferred — not stubbed, just absent.
- **Sequential inbox processing.** `/inbox` shows exactly one task (the
  oldest inbox item), never a list — per spec §7 ("traitement un par un,
  à la GTD"). An empty queue gets its own "boîte vide" message instead of
  an empty list.
- **Dedicated inbox action routes** — `POST /inbox/<id>/clarify`,
  `/inbox/<id>/defer`, `/inbox/<id>/delete` — instead of reusing
  `/tasks/<id>/clarify` etc. The existing task routes render/redirect to
  the task detail page; inbox actions must instead redirect back to
  `/inbox` so the next item comes up. They call the same
  `services/tasks.py` functions already built in 0.3.0 (`clarify`,
  `defer`, `delete`) — no service-layer changes.
- **Refine queue reuses the existing `/tasks/<id>/plan` route** for
  "attach to version" — no new route there. `/refine` itself only needs
  `?context=` and `?project_key=` query-string filters, read via
  `views.to_refine`.
- **Global capture** extends the existing `POST /tasks` handler
  (`routes_pages.tasks_list`) with an optional `next` form field (redirect
  target after capture), validated to start with `/` so it can only
  target this app (no open redirect). `base.html` grows a capture form
  present on **every** page, posting to `/tasks` with
  `next=request.path`, so capture never navigates away from the current
  page — per spec §6 ("sans quitter la page courante").
- **Keyboard shortcut.** A small vanilla-JS snippet in `base.html`: press
  `c` to focus the capture field, ignored while already typing in an
  input/textarea. No framework, no htmx dependency — per spec §7
  (server-rendered, no front-end dependency beyond local HTMX, which
  isn't wired in yet) and §6 ("il doit coûter une frappe").
- **Search** does a case-insensitive substring match on `Task.title` and
  `Task.body` (SQLite `LIKE`); an empty query string returns an empty
  list rather than the whole table.

### Files, in dependency order

1. **`src/services/views.py`** — the three functions above. Pure
   SQLAlchemy queries against `Task`/`Project`, no Flask import (ADR-0001,
   already enforced by `tests/test_architecture.py`'s AST guard).

2. **`tests/services/test_views.py`** — Given/When/Then style matching
   `tests/services/test_task.py`: `inbox()` returns only `INBOX`-state
   tasks in capture order; `to_refine()` returns only `REFINED` tasks with
   `version_id IS NULL`, filtered by `context`/`project_key` when given;
   `search()` matches a substring in title or body case-insensitively and
   returns `[]` for an empty term.

3. **`src/web/routes_pages.py`** — add:
   - `GET /inbox` — renders `inbox.html` with `views.inbox(session)[0]`
     (or `None`).
   - `POST /inbox/<int:task_id>/clarify` — calls `tasks.clarify`, catches
     `NotFoundError`/`ValidationError`/`InvalidTransitionError`, redirects
     to `/inbox` on success or re-renders `inbox.html` with the error and
     the same task on failure.
   - `POST /inbox/<int:task_id>/defer` — calls `tasks.defer`, same
     redirect/error pattern.
   - `POST /inbox/<int:task_id>/delete` — calls `tasks.delete`, redirects
     to `/inbox`.
   - `GET /refine` — reads `context`/`project_key` query args, renders
     `refine.html` with `views.to_refine(session, context, project_key)`
     and `projects.list(session)` (for the project filter dropdown).
   - `GET /search` — reads `q` query arg, renders `search.html` with
     `views.search(session, q)`.
   - Extend `tasks_list`'s POST branch: after `tasks.capture(...)`,
     redirect to `request.form.get("next")` if it starts with `/`,
     otherwise keep the current `url_for("pages.tasks_list")` fallback.

4. **`src/web/templates/inbox.html`, `refine.html`, `search.html`** —
   plain server-rendered forms/lists matching the existing style
   (`tasks.html`, `task.html`): no CSS framework, no JS beyond the
   shortcut in `base.html`.

5. **`src/web/templates/base.html`** — persistent capture form (`title`
   input + hidden `next` = current path) in the header, nav links to
   Inbox/Refine/Search, and the "press `c` to focus" script.

6. **`tests/web/test_pages.py`** — add: `GET /inbox` 200 (empty + with an
   item); clarify/defer/delete from `/inbox` advance to the next item;
   `GET /refine` filtered by context and by project_key; `GET
   /search?q=` finds a captured task by title; capturing from a
   non-`/tasks` page (e.g. `/projects`) with `next` set redirects back to
   that page, not to `/tasks`.

### End-to-end verification (= the 0.4.0 definition of done)

```bash
uv run pytest -q
FLASK_APP=src.app:create_app uv run flask run --host 127.0.0.1 --port 8765 &
curl -s http://127.0.0.1:8765/inbox
curl -s "http://127.0.0.1:8765/refine?context=@ordi"
curl -s "http://127.0.0.1:8765/search?q=docs"
kill %1
```
Manual: capture a task from `/projects` via the global capture bar and
confirm the page doesn't navigate away; find it in `/inbox`, clarify it,
plan it from `/refine`, then find it via `/search` — this is the DoD ("a
captured idea can reach a version without touching the DB by hand; a task
is findable via search").

### Critical files

- `src/services/views.py`
- `src/web/routes_pages.py`
- `src/web/templates/base.html`, `inbox.html`, `refine.html`, `search.html`
- `tests/services/test_views.py`, `tests/web/test_pages.py`

### After 0.4.0 lands

Per root `CLAUDE.md`, hand off to the `docs-manager` agent to update
`docs/architecture/overview.md` if the new read-only `views.py` layer
needs a mention, and to check off this increment before starting 0.5.0.

## Revisions

| Date | Section | Change | Reason |
|---|---|---|---|
| 2026-09-16 | 0.4.0 detailed plan | `services/queries.py` renamed `services/views.py` (incl. `tests/services/test_queries.py` → `test_views.py`) | "queries" is too generic — every service read is technically a query; the module is specifically the per-page read models (inbox/refine/search), which "views" names accurately. Matches the same rename in the spec (§5, §9). |
