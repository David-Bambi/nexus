---
status: accepted
date: 2026-11-19
---

# 0013 — A project / feature / task tree replaces planned versions

## Status

Accepted. Supersedes [0009](0009-version-lifecycle-in-cli-and-mcp.md),
[0010](0010-dod-editing-in-cli-and-mcp.md) and
[0011](0011-deleting-a-version.md); replaces the ref part of
[0006](0006-cli-shares-the-database.md) and the version actions of
[0002](0002-append-only-event-log.md).

## Decision

**Removed**: `Version`, `DefinitionOfDoneCriterion`, `services/versions.py`,
`events.changelog`, the dashboard's version progress, and every version or
DoD feature of the web UI, the CLI and the MCP server.

**Model** (diagram: [overview](../overview.md#domain-model)):

- `Project.parent_id`: a project can have subprojects, **one level only**
  (a subproject's parent is a root project; `projects.create` refuses a
  subproject as parent). A subproject has its own `key` plus an immutable
  `ref`; root projects have no ref.
- `Task` keeps its name and table and gains `kind` (`FEATURE` or `TASK`)
  and `parent_id` (the feature directly above). `project_id` is the nearest
  project or subproject; null on a raw capture.
- A task never has children; a feature holds features and tasks, no depth
  limit. No cycles: placing an item under itself or a descendant is refused.
  `tasks.move` keeps the state; moving a feature takes its subtree
  (descendants' `project_id` follows).
- `tasks.change_kind` turns a task into a feature, or a childless feature
  into a task.

**Refs**: `s-` (subproject), `f-` (feature), `t-` (task); `v-` is gone.
Features and tasks share one code namespace: `change_kind` respells
`t-4k2` to `f-4k2`, and either spelling resolves the item.
`projects.create` still refuses ref-shaped keys and command words.

**States**: `PLANNED` is removed.

- inbox → refined (clarify), someday (defer), cancelled
- refined → doing, someday, cancelled
- doing → waiting, done, cancelled
- waiting → doing, cancelled
- done → doing (reopen)
- someday → refined (clarify), cancelled
- cancelled → refined (restore)

Clarify can also set the parent feature and turn a capture into a feature.

**Closing and deleting**:

- Completing or cancelling a feature raises `ConflictError` while a child is
  neither done nor cancelled.
- Deleting a feature, a project or a subproject raises `ConflictError`
  unless it is empty; nothing cascades.

**Events** (on top of [0002](0002-append-only-event-log.md); version
actions, `planned` and `unplanned` are gone):

- task `kind_changed` `{from, to, ref: {from, to}}`;
- task `moved` `{from: {project, parent}, to: {project, parent}}` (project
  key, parent ref);
- task `created` carries `kind`, `project`, `parent` (capture: title only);
  task `clarified` carries `project`, `parent`; task `deleted` carries
  `title`, `kind`, `ref`;
- project `created` / `deleted` of a subproject carry `ref` (and `created`
  its `parent` key).

**Ids**: every table is `AUTOINCREMENT`, so a deleted id is never reused.
Events reference rows by `entity_type` + `entity_id`; a reused id mixed a
deleted row's history with a new one.

**Adapters**: the MCP server has 15 tools (7 read, 8 write); serialized
items carry `kind` and `parent`. Export rows carry `kind`, `parent_id` and
`ref`, with no `versions` section. Import format:
[0015](0015-tree-import-format.md).

## Why

Versions planned work by release, but the work itself is a breakdown:
a project into parts, parts into features, features into tasks. A tree
says what belongs to what; closing rules on features give the same "is it
finished" guard the version release gave, without a separate checklist.

## Known limits

- Lifted in increment 4: the MCP server now has clarify, move and
  change-kind tools ([MCP server](../../functional/mcp.md)).
- No migration from 1.x data: [0014](0014-restart-migrations-refuse-1x.md).

## Alternative rejected

Keeping versions next to the tree: two ways to group the same tasks, with
rules to keep them consistent.
