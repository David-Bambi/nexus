# Alembic in Nexus

Alembic manages the database schema as a sequence of versioned,
incremental changes — one revision file per change, applied in order.
The models in `src/models/` describe the schema Nexus *wants*; Alembic's
job is getting an existing SQLite file from whatever revision it's on to
that target, without ever hand-editing the schema directly.

## The revision chain

Each file in `src/migrations/versions/` declares a `revision` id and a
`down_revision` pointing at the previous one — a linked list. That chain,
not filenames or timestamps, defines the order migrations apply in. The
three revisions in this repo so far:

```
1ee9c901eec2  create initial schema        (down_revision: None)
      ↓
f7646852ba30  project status as enum       (down_revision: 1ee9c901eec2)
      ↓
0cd86ccf978f  version status and           (down_revision: f7646852ba30)
              task state as enum
```

`alembic upgrade head` walks this chain from the current position to the
last file; `alembic history` prints it.

## Commands

```bash
uv run alembic revision --autogenerate -m "..."   # diff models vs. DB, draft a migration
uv run alembic revision -m "..."                   # blank file, for hand-written changes
uv run alembic upgrade head                        # apply all pending revisions
uv run alembic downgrade -1                        # undo the last one
```

`src/app.py::_upgrade_database()` runs `alembic upgrade head`
automatically on every app startup (skipped when `TESTING` is set —
tests build the schema directly with `Base.metadata.create_all()`, see
`tests/conftest.py`). In practice you only run these commands by hand
while *authoring* a new migration, not to keep a running app up to date.

`src/migrations/env.py` sets `target_metadata = Base.metadata` — the
metadata `import src.models` registers every model onto — so autogenerate
diffs against exactly what's in `src/models/`, and reads
`Config.DATABASE_URL` from `src/config.py` rather than duplicating the DB
URL in `alembic.ini`.

## Autogenerate isn't magic

`--autogenerate` fails silently on some changes. When `Project.status`
moved from a plain string to a Python `Enum` (`ProjectStatus`, backed by
a SQLAlchemy `Enum` column with `create_constraint=True`),
`alembic revision --autogenerate` produced an **empty** upgrade/downgrade
— it doesn't reliably detect that a type change should add a SQLite
CHECK constraint. `f7646852ba30_project_status_as_enum.py` was written by
hand instead. Knowing autogenerate wouldn't catch the same pattern again,
`0cd86ccf978f_version_status_and_task_state_as_enum.py` (for
`Version.status` / `Task.state`) started from a blank
`alembic revision -m "..."`, skipping autogenerate entirely.

Lesson: always open the generated file and read it before trusting it.
If it's empty (or wrong) for a change you know you made, write it by
hand.

## Why `batch_alter_table`

SQLite has no `ALTER TABLE ADD CONSTRAINT` (and can't alter a column's
type in place). `op.batch_alter_table(...)` works around this
transparently: it creates a new table with the desired schema, copies the
data over, drops the old table, and renames — all inside the `with`
block. Both enum migrations use it:

```python
with op.batch_alter_table("project") as batch_op:
    batch_op.create_check_constraint(
        "project_status", "status IN ('ACTIVE', 'ARCHIVED')"
    )
```

with the matching `drop_constraint(..., type_="check")` in `downgrade()`.
Postgres and most other databases support `ALTER TABLE ADD CONSTRAINT`
directly and wouldn't need batch mode for the same change — it exists
specifically for SQLite's limitations.

## Dev loop

Change a model → generate a revision (or hand-write one, per the caveat
above) → `uv run alembic upgrade head` to apply it to your local dev DB
→ `uv run alembic downgrade -1` then `upgrade head` again to confirm the
round-trip actually works before considering the migration done. This is
exactly how both enum migrations were verified.
