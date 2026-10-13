---
status: accepted
date: 2026-10-13
---

# 0011 — Deleting a version

## Status

Accepted.

## Decision

`versions.delete(session, version_id, actor)` deletes the version and its
DoD criteria, whatever its status (released included). Its tasks are not
deleted:

- Unfinished tasks (`planned`, `doing`, `waiting`) go back to `refined`,
  with no version and no `blocked_reason`. Each logs a task `unplanned`
  event `{from, to: "REFINED", version: <version ref>}`.
- Other tasks (`done`, `cancelled`, `someday`) keep their state and lose
  the version link, with no task event.
- The version logs `deleted` `{project, number, title}`. Unknown id raises
  `NotFoundError`.

Web only: `POST /projects/<key>/versions/<number>/delete` (404 if unknown),
redirecting to the project page. The version page's "Delete version" button
stays disabled until the version number is typed, as for project deletion.
Not in the CLI or MCP server, like deleting tasks or projects
([0009](0009-version-lifecycle-in-cli-and-mcp.md),
[0010](0010-dod-editing-in-cli-and-mcp.md)).

## Why

- No work is lost: unfinished tasks return to the refine pool, ready to be
  planned into another version.
- Done history stays: done and cancelled tasks keep their state and
  `closed_at`; only the grouping disappears. The version's own events
  survive in the log ([0002](0002-append-only-event-log.md)).
- Released versions can be deleted, consistent with project deletion,
  which is allowed whatever the content.
- A destructive, rare action stays behind the web UI's typed confirmation.

## Alternative rejected

Cascade-deleting the tasks (as project deletion does): it would silently
drop unfinished work and completed history.
