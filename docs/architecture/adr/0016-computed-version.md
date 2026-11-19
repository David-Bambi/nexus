---
status: accepted
date: 2026-11-19
---

# 0016 — Computed version

## Status

Accepted. Builds on [0013](0013-project-feature-task-tree.md); extends the
import format of [0015](0015-tree-import-format.md) and the action
vocabulary of [0002](0002-append-only-event-log.md).

## Decision

Every project and subproject has a version `MAJOR.MINOR`, stored in
`project.version_major` / `project.version_minor` (int, not null, default
0) and kept up to date by `services/versioning.py`. A new project starts
at `0.0`.

**Minor**: completing a feature (`tasks.complete`) raises MINOR by 1 on its
nearest project (`task.project_id`; a subproject's version is independent
of its parent's). The feature records the version it shipped in, in
`task.released_in` (`"1.4"`; null on tasks and unshipped features).

- Once per feature: a feature reopened then completed again keeps its
  `released_in` and doesn't bump again.
- Reopening never lowers the version. Completing a task, cancelling a
  feature or moving a done feature changes no version.

**Major**: a project holds a list of criteria for its next major version
(`major_criterion`: `id`, `project_id`, `text`, `done`, `position`;
`AUTOINCREMENT`). Services add, update, check / uncheck and delete them.
`release_major` is refused (`ConflictError`) if the list is empty or a
criterion is unchecked; otherwise MAJOR + 1, MINOR = 0, and the list is
emptied.

**Direct set**: `set_version` sets a version, used when importing a new
project.

**Events**:

| Entity | Action | Payload |
|---|---|---|
| project | `minor_bumped` | `{from, to, feature}` (feature ref) |
| project | `major_released` | `{from, to, criteria}` (texts of the emptied list) |
| project | `version_set` | `{from, to}` |
| criterion | `criterion_added` | `{project, text}` |
| criterion | `criterion_updated` | `{project, text, previous}` |
| criterion | `criterion_checked` | `{project, text, from, to}` (check and uncheck) |
| criterion | `criterion_deleted` | `{project, text, done}` |

**Export / import**: the export gains a `criteria` table; projects carry
`version_major` / `version_minor`, tasks `released_in`. A newly created
project or subproject in an import accepts `"version": "MAJOR.MINOR"` and
`"criteria"` (strings or `{text, done}`); both are refused on an existing
project. `released_in` isn't importable (imported items are never done).

## Why

A version derived from the work done says where a project stands without
planning releases ([0013](0013-project-feature-task-tree.md) removed
them). Storing it gives stable, cheap reads; the event log still records
every change.

## Known limits

Exposed in the web UI and the MCP server; the CLI only shows the version and criteria (no write).

## Alternative rejected

- Computing the version from the event log on each read: costlier, and a
  read would depend on replaying history.
- Bumping again on every re-completion: reopening to fix a feature would
  inflate the version.
