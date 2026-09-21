---
status: accepted
date: 2026-09-21
---

# 0007 — The importer is the entry point for the MCP server

## Status

Accepted

## Decision

`services/importer.py` turns a JSON document (projects, versions, tasks)
into rows. It is transport-agnostic: no file, stdin or terminal access, so
the CLI (`nexus import`) and the MCP server call the same functions.

- `parse_text(text)`: one task title per line becomes an inbox-task document.
- `validate(session, data) -> list[str]`: collects **all** problems, each
  naming its entry; strict on unknown fields.
- `apply(session, data, actor, dry_run=False) -> ImportResult`: validates,
  then writes. Raises `ImportInvalid` (a `ValidationError` with `.errors`).
- **Natural keys**: projects match by `key`, versions by `number` within the
  project. An existing project or version is reused and never overwritten;
  its nested tasks are still created. Missing ones are created. Incoming
  refs and ids are not part of the format.
- **Tasks are always created**: no duplicate detection, importing twice
  duplicates them.
- **All-or-nothing**: everything is validated first, then applied in one
  transaction. Services commit per call, so `apply` hands them a stand-in
  session whose `commit` only flushes; the real session is committed or
  rolled back once. `dry_run` runs the whole thing, then rolls back and
  reports counts (refs hidden, nothing is stored).
- Format and rules: see [CLI](../../functional/cli.md#import).

## Why

Putting the rules in a service
now means agents get the same validation, atomicity and `actor` tagging
([0002](0002-append-only-event-log.md)) as the CLI, with no logic to
duplicate in a transport layer. Validating everything up front turns a bad
agent-written document into one complete error list instead of a half-done
import.

## Consequences and known limits

- The existing export (`services/export.dump_json`) is **not** re-importable:
  it carries raw integer ids and different shapes.
- Actor for imports is chosen by the caller (`cli` or `mcp`).
- The MCP server ([0008](0008-mcp-over-http-on-the-service.md)) exposes
  this as the `import_data` tool, next to the read tools.

## Alternative rejected

Importing the export format: it would need id remapping and conflict rules,
and couples the import contract to the backup format.
