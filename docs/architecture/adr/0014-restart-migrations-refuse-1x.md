---
status: accepted
date: 2026-11-19
---

# 0014 — Restart migrations, refuse 1.x databases

## Status

Accepted.

## Decision

- The migration history restarts at 2.0: a single initial migration,
  `87dc79bc1cbb` (`nexus_2_0_initial_schema`). The 1.x migrations are
  deleted.
- At startup, `create_app` checks the database's `alembic_version` before
  upgrading. A revision unknown to the code (any 1.x database) raises
  `UnsupportedDatabaseError`, naming the file and pointing to the README
  section "Upgrade from 1.x" (archive `data.db`, start on an empty one).
  A database without `alembic_version` is created normally.
- No data migration from 1.x.

## Why

The 2.0 model ([0013](0013-project-feature-task-tree.md)) has no place for
versions and their DoD; mapping them onto the tree would guess at meaning
for a single user who can re-import what matters
([0015](0015-tree-import-format.md)). Without the check, Alembic would fail
on the missing revision with an obscure error.

## Consequences

- The startup backup ([0005](0005-operational-layout.md)) still runs
  before the check, and the archived 1.x file stays readable.
- The CLI builds the app too ([0006](0006-cli-shares-the-database.md)), so
  it refuses a 1.x database the same way.
