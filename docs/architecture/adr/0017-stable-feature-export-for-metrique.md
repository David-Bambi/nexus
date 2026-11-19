---
status: accepted
date: 2026-11-19
---

# 0017 — Stable feature export for metrique

## Status

Accepted. Extends the project model of
[0013](0013-project-feature-task-tree.md) and the event vocabulary of
[0002](0002-append-only-event-log.md).

## Context

metrique (a separate repository) measured Nexus by reading its SQL tables
directly; the 2.0 schema broke it. Its unit of measure becomes the
feature, and it ties Claude Code sessions to projects by their `cwd`.

## Decision

**Project directory.** `project.directory` (nullable string, migration
`c7d2f4a1e835`): the project's folder on this machine.
`projects.normalize_directory` expands `~`, normalises the path and drops
the trailing slash; a relative path is refused (`ValidationError`); the
folder need not exist. A subproject without one inherits its parent's
(`projects.directory_of`). Set through the web forms (new project, new
subproject, edit) and MCP `create_project` / `update_project`
(`directory`: blank clears, omitted keeps, `projects.KEEP`). Logged in the
project's `created` / `updated` payloads.

**Correction.** `tasks.update(correction=True)` logs `corrected` instead
of `updated`, same payload. Web: "Correction" checkbox on the item edit
form; MCP: `update_task` `correction` boolean. Plan-drift measures can
ignore fixes (typo, wrong size).

**Parent in every task event.** Every task event payload carries `parent`:
the ref of the parent feature at that moment, or null
(`tasks._log`). Drift stays attributable after a move.

**Plan freeze.** On a feature's first start, the `started` payload
carries `plan`: the refs of its children, in sibling order. Later starts
don't.

**Export contract `nexus.features/1`** (`services/export.features`,
`FEATURES_SCHEMA`):

```
{"schema": "nexus.features/1", "exported_at",
 "features": [{"ref", "title", "state", "project", "directory",
               "started_at", "closed_at", "released_in", "plan",
               "children": [{"ref", "kind", "title", "state", "size"}],
               "events": [{"at", "actor", "ref", "action", "payload"}]}]}
```

- One entry per feature, creation order. `project` is the nearest
  project's key, `directory` its effective directory, `started_at` the
  first start, `plan` the frozen plan (null if never started).
- `events`, oldest first: the feature's own, plus a child's event when
  the child was under the feature at that moment (`payload.parent`), plus
  a `moved` out of it (`from.parent`). A deleted child's events keep its
  ref.
- All dates UTC with an explicit `+00:00` (Nexus stores naive UTC;
  metrique's docs wrongly assume local time).
- The schema version is bumped when a field is removed or changes
  meaning; adding a field keeps it.

**Access.** CLI `nexus export features [-o FILE]` (stdout by default);
web `GET /export/features.json` (inline JSON). No MCP tool: metrique
reads offline.

`export` joins the reserved project keys.

## Why

A versioned export decouples metrique from the schema: Nexus can change
its tables while the contract holds. `parent`, `plan` and `corrected` give
the facts a plan-drift measure needs, recorded at the moment they happen.

## Consequences

metrique's collector must be rewritten to read this export (out of
Nexus' scope).

## Alternative rejected

- Keeping metrique on the SQL tables: breaks on every schema change.
- An MCP tool: needs the service running.
