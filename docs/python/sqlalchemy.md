# SQLAlchemy in Nexus

SQLAlchemy is the ORM: it maps Python classes in `src/models/` to SQL
tables and turns attribute access into queries. Alembic, built on top of
it, diffs those class definitions against the live database and generates
migration scripts to bring the schema in line — so the schema is never
edited by hand, only ever derived from the models.

## How the pieces connect

```mermaid
flowchart TD
    CFG["Config.DATABASE_URL<br/>(src/config.py)"] --> ENGINE
    ENGINE["get_engine()<br/>(src/db.py) → Engine"]
    ENGINE --> FACTORY["get_session_factory()<br/>(src/db.py) → scoped_session"]
    FACTORY --> SESSION["one Session per request/thread"]
    TEARDOWN["teardown_appcontext<br/>_remove_session (src/app.py)"] -->|removes| SESSION

    BASE["Base = DeclarativeBase<br/>(src/db.py)"] --> M1["Project"]
    BASE --> M2["Version"]
    BASE --> M3["Task"]
    BASE --> M4["Tag"]
    BASE --> M5["Event"]
    M1 & M2 & M3 & M4 & M5 --> META["Base.metadata<br/>(full schema)"]

    META --> AUTOGEN["Alembic autogenerate<br/>(src/migrations/env.py)"]
    AUTOGEN --> VERSIONS["migration scripts<br/>(src/migrations/versions/)"]
    VERSIONS -->|applied to| ENGINE

    SESSION --> SVC["services/*<br/>(ADR-0001)"]
    SVC -->|query / add / commit| SESSION
```

`services/` receives the `Session` as a plain argument — it never imports
Flask, never touches `app.extensions`, so the same functions work from a
route, a test, or (eventually) a CLI or agent.

## Request lifecycle vs. tests

In the running app, `create_app()` builds one `Engine` and one
thread-scoped `Session` factory for the whole process. A `Session` is
created lazily on first use within a request and released by
`_remove_session` in `teardown_appcontext` once the request ends — so
each request effectively gets its own `Session`, without the app code
having to manage that explicitly.

A service test skips all of this: the `session` fixture
(`tests/conftest.py`) builds its own in-memory SQLite `Engine` and
`Session` directly, with `Base.metadata.create_all()` for tables — no
Flask app, no request, no teardown hook involved.
