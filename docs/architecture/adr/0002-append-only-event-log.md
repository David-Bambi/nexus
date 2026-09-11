---
status: accepted
date: 2026-09-11
---

# 0002 — Append-only event log

## Status

Accepted

## Decision

Every domain mutation writes an immutable row to the `event` table. The
log is never updated or deleted.

## Why

Near-zero cost now, impossible to retrofit later. It provides per-task
history, an automatic per-version changelog, and — critically — traceability
of what an agent will have modified once agentic capabilities arrive. The
`actor` field is `"web"` in V1 and will later distinguish `cli` and `agent`.
