---
status: accepted
date: 2026-10-11
---

# 0010 — DoD editing in the CLI and the MCP server

## Status

Accepted. Narrows [0009](0009-version-lifecycle-in-cli-and-mcp.md)
("DoD editing stays web-only"), and with it the scope limits of
[0006](0006-cli-shares-the-database.md) and
[0008](0008-mcp-over-http-on-the-service.md).

## Decision

- **CLI**: version actions (after `<project> <version>` or a `v-` ref)
  `add-criterion <text…>`, `edit-criterion <n> <text…>` and
  `remove-criterion <n>`; the remaining words, joined by spaces, are the
  text. In `cli/views.py` (`VERSION_ACTIONS`), actor `cli`, then the version
  detail is printed. Usage: [Command line](../../functional/cli.md).
- **MCP**: write tools `add_criterion` (`version`, `project`,
  `description`), `update_criterion` (`+ index`, `description`) and
  `delete_criterion` (`+ index`), `index` counted from 1 as listed by
  `get_version`. They return the version like `get_version`, are not
  idempotent, and share the `_criterion_at` index check with
  `set_criterion_done`. `Tool` gained a `destructive` flag:
  `delete_criterion` is the only tool with `destructiveHint: true`. 25 tools
  in all. Usage: [MCP server](../../functional/mcp.md).
- Rules stay in `services/versions.py` (`add_criterion`, `update_criterion`,
  `delete_criterion`, already used by the web UI): a released version is
  locked (`ConflictError`), blank text is refused, the last criterion can't
  be deleted, and each change logs a `dod_added` / `dod_updated` /
  `dod_deleted` event.

## Why

An assistant working through MCP found DoD criteria contradicting later
decisions and could neither reword nor delete them; the CLI had the same
gap. The services already guard the DoD, so exposing them adds no new rule.
Deleting tasks or projects and archiving stay web-only.
