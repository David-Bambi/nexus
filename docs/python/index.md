# Python

Generic Python and library concept explainers, grounded in this project's
own code but not themselves decisions about Nexus's architecture — those
live under [Architecture](../architecture/overview.md) instead.

- [SQLAlchemy in Nexus](sqlalchemy.md) — engine, sessions, and how Alembic
  derives migrations from the models.
- [Context managers (`with`)](context-managers.md) — the protocol behind
  `with`, grounded in examples from `src/migrations/env.py` and
  `tests/test_project.py`.
- [Alembic migrations](alembic.md) — the revision chain, autogenerate's
  limits, and why `batch_alter_table` exists, grounded in the three
  migrations under `src/migrations/versions/`.
- [Function declarations](function-declarations.md) — `def` shape,
  positional vs. default arguments, type hints, keyword-only arguments,
  and docstrings.
