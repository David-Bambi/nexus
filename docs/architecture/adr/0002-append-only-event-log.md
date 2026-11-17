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
`actor` field is `"web"`, `"cli"` (see
[0006](0006-cli-shares-the-database.md)) or `"mcp"` (see
[0008](0008-mcp-over-http-on-the-service.md)), which tells what an agent
modified.

## Implementation

Written through `services/events.log(session, actor, entity_type,
entity_id, action, payload=None)`. `actor` is required; services pass the
constant `events.ACTOR_WEB` (`"web"`), `events.ACTOR_CLI` (`"cli"`) or
`events.ACTOR_MCP` (`"mcp"`). Every mutating service takes an `actor`
argument, default `web`.

**Same transaction.** `log()` only `session.add()`s the event; the calling
service commits it with the mutation, so both are stored or neither. A
refused call (validation, invalid transition) raises before logging and
leaves no event. The session runs with `autoflush=False`, so services
`flush()` before logging a `created` event to obtain the new id.

**Action vocabulary.**

| Entity | Actions |
|---|---|
| task | `created`, `updated`, `clarified`, `planned`, `unplanned`, `started`, `blocked`, `unblocked`, `completed`, `reopened`, `deferred`, `cancelled`, `restored`, `moved`, `deleted` |
| version | `created`, `started`, `released`, `deleted`, `dod_added`, `dod_updated`, `dod_deleted`, `dod_checked`, `dod_unchecked` |
| project | `created`, `archived`, `deleted`, `versions_reordered` |

`versions_reordered` is logged on the project, with payload `ordered_ids`.

`dod_*` events are logged on the version (Definition of Done criteria have no
entity of their own in the log). `dod_checked` / `dod_unchecked` are skipped
when the state doesn't change.

**Payload convention.**

- State changes: `{"from", "to"}` (state names), plus `version_id` on
  `planned` and `reason` on `blocked`. `moved` carries `{from, to,
  from_version_id, version_id}` (`from` / `to` are the unchanged state
  name, `version_id` the target). `unplanned` from a version deletion
  carries `{from, to, version}` (`version` is the deleted version's ref,
  see [0011](0011-deleting-a-version.md)).
- `updated`: only the changed fields, as `{field: {"from", "to"}}`. No
  event if nothing changed.
- `created` / `deleted`: carry the title (or key/name/number) so a deleted
  entity's history stays readable.

**Reads.** `events.history(entity_type, entity_id)` returns one entity's
events, oldest first. `events.changelog(version_id)` returns the version's
own events plus those of the tasks currently in it, so deleted or
unplanned tasks drop out. Both use the `ix_event_entity` index on
`event(entity_type, entity_id)`.

## Known gaps

- Deleting a project cascades to its versions and tasks without events for
  them; only the project's `deleted` event is logged.
- `archive` logs an event even if the project is already archived.
