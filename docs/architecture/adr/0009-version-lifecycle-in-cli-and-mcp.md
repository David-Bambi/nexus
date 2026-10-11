---
status: accepted
date: 2026-09-23
---

# 0009 — Version lifecycle in the CLI and the MCP server

## Status

Accepted. Narrows the scope limits of
[0006](0006-cli-shares-the-database.md) and
[0008](0008-mcp-over-http-on-the-service.md).

## Decision

- **CLI**: actions after a version reference (`<project> <version>` or a
  `v-` ref): `check <n>` / `uncheck <n>` (DoD criterion, from 1), `start`,
  `release`. They live in `cli/views.py` (`VERSION_ACTIONS`), call
  `versions.set_criterion_done` / `start` / `release` with actor `cli`, then
  print the version detail. Usage: [Command line](../../functional/cli.md).
- **MCP**: write tools `start_version` and `release_version` (arguments
  `version`, `project`), returning the version like `get_version`. Not
  idempotent: a repeated call is refused by the status rule.
  Usage: [MCP server](../../functional/mcp.md).
- Rules stay in the services: `release` is refused while a task is
  unfinished (cancelled ones don't count) or a criterion is unchecked.

## Why

Closing a version is the natural end of work done from the terminal or by
an assistant; having to switch to the web UI for it was the main gap. The
release guard in `services/versions.py` already protects the data, so
exposing the transitions adds no new rule. Deleting, archiving and DoD
editing stay web-only.

DoD editing was later exposed by
[0010](0010-dod-editing-in-cli-and-mcp.md).
