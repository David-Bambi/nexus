---
status: accepted
date: 2026-09-21
---

# 0006 — The CLI shares the database, tasks and versions get refs

## Status

Accepted

## Decision

- **Transport**: the `nexus` CLI (`src/cli/`) imports `services/` directly
  and works on the same SQLite database as the running service (WAL allows a
  reader and a writer side by side). There is no HTTP API.
- **Session**: `cli/session.py` builds the Flask app with `create_app` only
  to obtain the session, so the CLI resolves the same database as the
  service (`NEXUS_HOME` / `NEXUS_DATABASE_URL`).
- **Entry point**: `nexus = "src.cli:main"` in `pyproject.toml`; also
  `python -m src.cli`. Making `uv sync` install the project required a
  `[build-system]` (hatchling, `packages = ["src"]`).
- **Exit codes**: 0 success, 1 domain error (a service refused the
  request), 2 usage error (unknown command, missing argument).
- **Refs**: tasks and versions carry a short, unique, immutable `ref`
  (`t-4k2`, `v-9xa`: prefix, dash, base36 code of 3 characters). It is
  generated at creation by `services/refs.py`; on collisions the code grows
  by one character every 5 attempts. Migration `a4f19c2e7b31` adds the
  column and backfills existing rows. Lookups: `tasks.get_by_ref`,
  `versions.get_by_ref`, case-insensitive. Projects keep their `key`.
  Refs are shown in the web UI (task and version pages and lists).
- **Reference resolution**: a `t-` / `v-` shaped argument is a task or
  version, anything else a project key. To keep this unambiguous,
  `projects.create` refuses ref-shaped keys and the command words `add`,
  `help`, `import`, `projects`, `tasks`, `version`, `versions`
  (`ValidationError`, shown by the web form).
- **Actor**: `events.ACTOR_CLI = "cli"`. The creation services
  (`projects.create`, `versions.create`, `tasks.capture`, `tasks.create`,
  `tasks.create_in_version`) take an `actor` argument, default `web`.

## Why

A single-user local tool doesn't need a second network surface: an HTTP API
would need to be designed, versioned, and kept localhost-only next to
[0004](0004-localhost-only.md), for no benefit over calling the services
the web pages already use ([0001](0001-services-ignore-http.md)). Refs give
the command line an identifier short enough to type; integer ids are
internal and a project key alone can't name a task.

## Consequences and known limits

- Building the app applies pending migrations. Running the CLI against the
  real database can therefore migrate it **before the service is
  redeployed**, and without the startup backup of
  [0005](0005-operational-layout.md) (that backup is taken by `src.main`, not
  by `create_app`).
- `services/` stays framework-agnostic; `tests/test_architecture.py`
  enforces it.
- The CLI cannot edit, change a task's state or toggle a DoD criterion.
  Only the creation services take `actor`; other mutations still log `web`.
- Task title validation for capture/create lives in the CLI and the importer,
  not in the services.

## Alternative rejected

A local HTTP API consumed by the CLI: more moving parts, needs the service
to be running, and adds a surface to protect.
