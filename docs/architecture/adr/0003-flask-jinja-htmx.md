---
status: accepted
date: 2026-09-11
---

# 0003 — Flask, Jinja, HTMX, no build step

## Status

Accepted

## Decision

Flask as the server, Jinja for templates, HTMX for interactivity,
SQLAlchemy for persistence, Alembic for migrations, SQLite as the engine.

## Why

HTMX gives the expected responsiveness (check a task, move a task to a
version, refresh a fragment) while staying entirely server-side Python. No
npm, no bundler, no second language to maintain. SQLite as a single file
simplifies backup and portability.

## Alternative rejected

FastAPI would give a typed API out of the box, but imposes a front/back
decoupling that's unnecessary for a local, single-user app.
