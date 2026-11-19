---
status: accepted
date: 2026-11-19
---

# 0015 — Tree import format

## Status

Accepted. Replaces the document format of
[0007](0007-importer-mcp-entry-point.md); the rest of 0007 still holds
(all-or-nothing, `dry_run`, natural keys, unknown fields rejected, tasks
always created).

## Decision

```
{"projects": [{"key", "name", "description",
               "items": [ITEM],
               "subprojects": [{"key", "name", "description", "items": [ITEM]}]}],
 "tasks": [{"title", "body", "context", "size", "project"}]}

ITEM = {"kind": "feature" | "task" (default "task"), "title", "body",
        "context", "size", "children": [ITEM]}   # children: features only
```

- Projects and subprojects match by `key`; an existing one is reused,
  never overwritten. An existing project can't change place (a root project
  listed as a subproject, or the reverse, or under another parent, is an
  error).
- Items in a project tree are created `refined`; loose `tasks` land in the
  inbox, in `project` if given (declared in the document or existing).
- `children` on a task is an error; a key declared twice is an error.
- `ImportResult.created` lists `(kind, ref, title)` per item.
- Usage: [CLI import](../../functional/cli.md#import).

## Why

The format follows the model ([0013](0013-project-feature-task-tree.md)):
an assistant can hand over a whole breakdown in one document. Items placed
in a tree are already clarified, so they skip the inbox.
